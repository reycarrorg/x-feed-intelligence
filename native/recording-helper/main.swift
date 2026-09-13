import AppKit
import AVFoundation
import CoreMedia
import CoreVideo
import Foundation
import Vision

enum HelperError: Error {
    case invalidArguments
    case noVideoTrack
    case invalidDuration
    case writer(String)
}

func emit(_ value: Any) throws {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
}

func metadata(_ path: String) async throws {
    let url = URL(fileURLWithPath: path)
    let attributes = try FileManager.default.attributesOfItem(atPath: path)
    let asset = AVURLAsset(url: url)
    let duration = try await asset.load(.duration)
    let tracks = try await asset.loadTracks(withMediaType: .video)
    guard let track = tracks.first else { throw HelperError.noVideoTrack }
    let size = try await track.load(.naturalSize)
    let transform = try await track.load(.preferredTransform)
    let transformed = size.applying(transform)
    let descriptions = try await track.load(.formatDescriptions)
    let codec: String
    if let description = descriptions.first {
        let subtype = CMFormatDescriptionGetMediaSubType(description)
        codec = String(format: "%c%c%c%c", (subtype >> 24) & 255, (subtype >> 16) & 255, (subtype >> 8) & 255, subtype & 255)
    } else {
        codec = "unknown"
    }
    try emit([
        "status": "OK",
        "duration_seconds": CMTimeGetSeconds(duration),
        "width": Int(abs(transformed.width)),
        "height": Int(abs(transformed.height)),
        "codec": codec,
        "file_bytes": (attributes[.size] as? NSNumber)?.int64Value ?? 0,
        "video_track_count": tracks.count,
    ])
}

func recognize(_ image: CGImage) throws -> [[String: Any]] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .fast
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    return (request.results ?? []).compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return ["text": candidate.string, "confidence": Double(candidate.confidence), "box": [box.origin.x, box.origin.y, box.size.width, box.size.height]]
    }
}

func ocr(_ path: String, crop: [Int], intervalMilliseconds: Int) async throws {
    let asset = AVURLAsset(url: URL(fileURLWithPath: path))
    let duration = try await asset.load(.duration)
    let seconds = CMTimeGetSeconds(duration)
    guard seconds.isFinite && seconds > 0 else { throw HelperError.invalidDuration }
    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.requestedTimeToleranceBefore = .zero
    generator.requestedTimeToleranceAfter = .zero
    let interval = max(1, intervalMilliseconds)
    var frames: [[String: Any]] = []
    var current = 0
    while Double(current) / 1000.0 < seconds && frames.count < 250 {
        let time = CMTime(value: CMTimeValue(current), timescale: 1000)
        let (fullImage, actualTime) = try await generator.image(at: time)
        let imageWidth = fullImage.width
        let imageHeight = fullImage.height
        let x = max(0, min(crop[0], imageWidth - 1))
        let yTop = max(0, min(crop[1], imageHeight - 1))
        let width = min(crop[2], imageWidth - x)
        let height = min(crop[3], imageHeight - yTop)
        let y = imageHeight - yTop - height
        guard let cropped = fullImage.cropping(to: CGRect(x: x, y: max(0, y), width: width, height: height)) else { throw HelperError.invalidArguments }
        frames.append(["video_time_ms": Int(CMTimeGetSeconds(actualTime) * 1000), "text": try recognize(cropped)])
        current += interval
    }
    try emit(["status": "OK", "ocr_engine": "Apple Vision", "worker_count": 1, "candidate_frame_count": frames.count, "frames": frames])
}

func drawFrame(width: Int, height: Int, lines: [String]) throws -> CVPixelBuffer {
    var pixelBuffer: CVPixelBuffer?
    let options = [kCVPixelBufferCGImageCompatibilityKey: true, kCVPixelBufferCGBitmapContextCompatibilityKey: true] as CFDictionary
    let status = CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32ARGB, options, &pixelBuffer)
    guard status == kCVReturnSuccess, let buffer = pixelBuffer else { throw HelperError.writer("pixel-buffer") }
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard let base = CVPixelBufferGetBaseAddress(buffer) else { throw HelperError.writer("pixel-base") }
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    guard let context = CGContext(data: base, width: width, height: height, bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(buffer), space: colorSpace, bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue) else { throw HelperError.writer("context") }
    context.setFillColor(NSColor.black.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    let graphics = NSGraphicsContext(cgContext: context, flipped: false)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = graphics
    let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 42, weight: .semibold), .foregroundColor: NSColor.white]
    for (index, line) in lines.enumerated() {
        NSString(string: line).draw(at: CGPoint(x: 70, y: height - 120 - index * 76), withAttributes: attributes)
    }
    NSGraphicsContext.restoreGraphicsState()
    return buffer
}

func generateSynthetic(_ path: String) async throws {
    let url = URL(fileURLWithPath: path)
    try? FileManager.default.removeItem(at: url)
    let writer = try AVAssetWriter(outputURL: url, fileType: .mov)
    let width = 1280, height = 720
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height])
    input.expectsMediaDataInRealTime = false
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB, kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height])
    guard writer.canAdd(input) else { throw HelperError.writer("cannot-add") }
    writer.add(input)
    guard writer.startWriting() else { throw HelperError.writer("start") }
    writer.startSession(atSourceTime: .zero)
    let cards = [
        ["Synthetic Recorder", "Deterministic local workshop on day 7", "Organic"],
        ["Synthetic Recorder", "Deterministic local workshop on day 7", "Organic"],
        ["Example Studio", "Invented notebook offer", "Promoted"],
        ["Unknown", "Partial evidence", "Review required"],
    ]
    for (index, card) in cards.enumerated() {
        while !input.isReadyForMoreMediaData { try await Task.sleep(for: .milliseconds(5)) }
        let buffer = try drawFrame(width: width, height: height, lines: card)
        guard adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(index), timescale: 1)) else { throw HelperError.writer("append") }
    }
    input.markAsFinished()
    await writer.finishWriting()
    guard writer.status == .completed else { throw HelperError.writer("finish") }
    try emit(["status": "OK", "kind": "AUTHORED_SYNTHETIC_RECORDING", "frame_count": cards.count])
}

@main
struct Main {
    static func main() async {
        do {
            let args = CommandLine.arguments
            guard args.count >= 3 else { throw HelperError.invalidArguments }
            switch args[1] {
            case "metadata": try await metadata(args[2])
            case "ocr":
                guard args.count == 8, let x = Int(args[3]), let y = Int(args[4]), let w = Int(args[5]), let h = Int(args[6]), let interval = Int(args[7]), w > 0, h > 0 else { throw HelperError.invalidArguments }
                try await ocr(args[2], crop: [x, y, w, h], intervalMilliseconds: interval)
            case "generate-synthetic": try await generateSynthetic(args[2])
            default: throw HelperError.invalidArguments
            }
        } catch {
            try? emit(["status": "ERROR", "code": "NATIVE_RECORDING_FAILURE"])
            Foundation.exit(2)
        }
    }
}

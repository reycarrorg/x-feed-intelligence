import Foundation
import JavaScriptCore

guard CommandLine.arguments.count == 2 else { exit(2) }
let script = try String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8)
guard let context = JSContext() else { exit(2) }
var failure: String?
context.exceptionHandler = { _, exception in failure = exception?.toString() ?? "javascript-exception" }
context.evaluateScript(script)
let tests = #"""
(function () {
  const H = XFIHarness;
  let now = 0;
  const clock = () => now;
  const h = new H.Harness(clock);
  const base = {origin:H.RESERVED_ORIGIN, nodeKey:"node-a", identity:"post-a", visibleText:"Authored synthetic card", promotion:"organic", relationships:[], topology:"reviewed-v1", topLevel:true, ambiguityRatio:0, documentVisible:true, visibilityRatio:0.5};
  const lifecycle = [h.state, h.userArm(H.RESERVED_ORIGIN), h.state, h.userStart(), h.state];
  const edgeAccepted = h.candidate(base);
  const sameIdentityMutation = h.candidate(Object.assign({}, base, {visibleText:"Authored synthetic card updated"}));
  const reusedNodeAccepted = h.candidate(Object.assign({}, base, {identity:"post-b", visibleText:"Second authored card"}));
  h.documentHidden();
  const hiddenAccepted = h.candidate(Object.assign({}, base, {nodeKey:"hidden", identity:"hidden"}));
  h.documentVisible();
  const belowAccepted = h.candidate(Object.assign({}, base, {nodeKey:"below", identity:"below", visibilityRatio:0.499999}));
  const exportValue = h.userExport();
  h.userStop();
  const stopped = h.snapshot();
  const postStopAccepted = h.candidate(Object.assign({}, base, {nodeKey:"late", identity:"late"}));
  const stopResults = {};
  H.HARD_STOPS.forEach((code) => {
    const instance = new H.Harness(clock);
    instance.userArm(H.RESERVED_ORIGIN); instance.userStart(); instance.hardStop(code);
    const before = instance.snapshot();
    const later = instance.candidate(base);
    const after = instance.snapshot();
    stopResults[code] = {state:before.state, observerCount:before.observerCount, timerCount:before.timerCount, domReferenceCount:before.domReferenceCount, postStopAccepted:later, queueStable:before.queueCount === after.queueCount};
  });
  return JSON.stringify({
    lifecycle, edgeAccepted, sameIdentityMutation, reusedNodeAccepted, hiddenAccepted, belowAccepted,
    exportRecordCount: exportValue.records.length, stopped, postStopAccepted, stopResults,
    capabilities: {fetch:typeof fetch, xhr:typeof XMLHttpRequest, websocket:typeof WebSocket, document:typeof document},
  });
})()
"""#
let result = context.evaluateScript(tests)
if failure != nil || result == nil { exit(2) }
print(result!.toString()!)


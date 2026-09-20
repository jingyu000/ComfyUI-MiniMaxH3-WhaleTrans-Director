// Shared, frame-based timeline geometry; also exercised without a browser.
export const FPS = 24;
export const MAX_LENGTH = 3592;
export function alignedLength(frames, minimum = 5) {
  const lower = 5 + 17 * Math.max(0, Math.ceil((minimum - 5) / 17));
  return Math.min(MAX_LENGTH, Math.max(lower, 5 + 17 * Math.max(0, Math.round((frames - 5) / 17))));
}
export function nearestOverlap(frames, maximum) {
  const choices = [0, 1, ...Array.from({length:Math.max(0, Math.floor((maximum - 5) / 17) + 1)}, (_,i)=>5+17*i)]
    .filter(n=>n<=maximum);
  return choices.reduce((best,n)=>Math.abs(n-frames)<Math.abs(best-frames)?n:best,0);
}
export function createWindows(previous, count, defaultFrames) {
  const result=[];
  for(let i=0;i<count;i++) {
    const old=previous[i]||{}, prev=result[i-1];
    const length=alignedLength(Number.isInteger(old.endFrame)?old.endFrame-old.startFrame:defaultFrames);
    const overlap=prev?nearestOverlap(Number.isInteger(old.startFrame)?prev.endFrame-old.startFrame:39,Math.min(length,prev.endFrame-prev.startFrame)-1):0;
    const start=prev?prev.endFrame-overlap:0;
    result.push({...old, enabled: old.enabled!==false, images:[...(old.images||[])],audios:[...(old.audios||[])],prompt:old.prompt||"",startFrame:start,endFrame:start+length});
  }
  return result;
}
export function editWindow(windows, index, mode, frame) {
  const result=windows.map(s=>({...s})), s=result[index], prev=result[index-1], next=result[index+1];
  if(!s)return result;
  const oldEnd=s.endFrame, oldLength=s.endFrame-s.startFrame;
  const outgoing=next?s.endFrame-next.startFrame:0;
  if(mode==='move'||mode==='left') {
    const incoming=prev?nearestOverlap(prev.endFrame-Math.round(frame),Math.min(prev.endFrame-prev.startFrame,oldLength)-1):0;
    s.startFrame=prev?prev.endFrame-incoming:0;
    const length=mode==='move'?oldLength:alignedLength(oldEnd-s.startFrame,Math.max(incoming,outgoing)+1);
    s.endFrame=s.startFrame+length;
  } else {
    const incoming=prev?prev.endFrame-s.startFrame:0;
    s.endFrame=s.startFrame+alignedLength(Math.round(frame)-s.startFrame,Math.max(incoming,outgoing)+1);
  }
  // Ripple subsequent windows to preserve their lengths and existing seam overlaps.
  const delta=s.endFrame-oldEnd;
  for(let i=index+1;i<result.length;i++){result[i].startFrame+=delta;result[i].endFrame+=delta;}
  return result;
}

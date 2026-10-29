// Render actual source excerpts, synthesize local narration, and append the live UI recording.
import {chromium} from '@playwright/test';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=fileURLToPath(new URL('../',import.meta.url));
const work=root+'.local/video-build/';mkdirSync(work,{recursive:true});
const chapters=JSON.parse(readFileSync(root+'video/chapters.json','utf8'));
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1920,height:1080}});
const files=[];
for(let i=0;i<chapters.length;i++){
 const c=chapters[i],source=readFileSync(root+c.file,'utf8').split('\n'),start=source.findIndex(l=>l.includes(c.start));
 if(start<0)throw Error('Code anchor absent');
 const code=source.slice(start,start+c.lines).map((l,n)=>String(start+n+1).padStart(3)+'  '+l).join('\n');
 await page.setContent(`<html><head><style>body{margin:0;background:#f5f4ed;color:#213c31;font-family:Arial;padding:65px}small{letter-spacing:3px;font-size:20px}h1{font-family:Georgia;font-weight:400;font-size:52px;margin:28px 0}pre{background:#203c32;color:#e8f0e4;padding:30px;border-radius:15px;font-size:22px;line-height:1.18;white-space:pre-wrap;margin:24px 0}footer{font-size:20px;color:#657369}</style></head><body><small>PART E / CODE & EXECUTION WALKTHROUGH / ${i+1} OF ${chapters.length}</small><h1>${esc(c.title)}</h1><footer>${esc(c.file)} · actual repository excerpt</footer><pre>${esc(code)}</pre><footer>PostgreSQL substitution approved · Local demonstration · Synthesized narration</footer></body></html>`);
 await page.screenshot({path:work+i+'.png'});
 writeFileSync(work+i+'.txt',c.narration);
 execFileSync('say',['-r','165','-f',work+i+'.txt','-o',work+i+'.aiff']);
 const duration=Number(execFileSync('ffprobe',['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',work+i+'.aiff'],{encoding:'utf8'}).trim());
 const out=work+i+'.mp4';
 execFileSync('ffmpeg',['-y','-loglevel','error','-loop','1','-framerate','25','-i',work+i+'.png','-i',work+i+'.aiff','-c:v','libx264','-preset','fast','-crf','24','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2','-t',String(duration+.4),out]);files.push(out);
 console.log('Rendered chapter '+(i+1));
}
await browser.close();
const video=readFileSync(root+'.local/browser-video.txt','utf8').trim();
const out=work+'browser.mp4';
execFileSync('ffmpeg',['-y','-loglevel','error','-i',video,'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2','-r','25','-c:v','libx264','-preset','fast','-crf','24','-pix_fmt','yuv420p','-c:a','aac','-shortest',out]);files.push(out);
writeFileSync(work+'concat.txt',files.map(f=>"file '"+f+"'").join('\n'));
execFileSync('ffmpeg',['-y','-loglevel','error','-f','concat','-safe','0','-i',work+'concat.txt','-c','copy','-movflags','+faststart',root+'video/part-e-walkthrough.mp4']);
console.log('Narrated code walkthrough and actual browser recording saved.');

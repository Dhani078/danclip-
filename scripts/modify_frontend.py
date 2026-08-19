import re

def modify():
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. CDN tailwind -> static/styles.css
    content = content.replace(
        '<script src="https://cdn.tailwindcss.com"></script>',
        '<link rel="stylesheet" href="/static/styles.css">'
    )
    # Remove tailwind.config script block
    content = re.sub(r'<script>\s*tailwind\.config = {.*?</script>', '', content, flags=re.DOTALL)

    # 2. text-[9px] and text-[10px] -> text-[11px]
    content = content.replace('text-[9px]', 'text-[11px]')
    content = content.replace('text-[10px]', 'text-[11px]')

    # 3. text-zinc-500 -> text-zinc-400
    content = content.replace('text-zinc-500', 'text-zinc-400')

    # 4. updateUI: prevent re-rendering clips on every SSE tick.
    # We will wrap the `if (job.clips_json)` block inside `if (job.status === 'COMPLETED')`
    # or handle it better. Wait, we still need to render clips if they exist?
    # Let's replace the whole updateUI function.
    updateUI_pattern = r'function updateUI\(job\) \{.*?(?=async function publishTikTokWithMode)'
    
    new_updateUI = """function updateUI(job) {
            statusBadge.textContent = job.status;

            statusBadge.className = 'text-[11px] font-mono px-2 py-0.5 rounded-full uppercase tracking-wider ' +
                (job.status === 'COMPLETED' ? 'bg-emerald-500/10 text-emerald-500' :
                    job.status === 'FAILED' ? 'bg-rose-500/10 text-rose-500' :
                        job.status === 'QUEUED' ? 'bg-zinc-800 text-zinc-400' :
                            'bg-amber-500/10 text-amber-500');

            progressBar.style.width = `${job.progress_percentage}%`;
            if (job.status === 'FAILED') {
                progressBar.classList.add('bg-rose-500');
                progressBar.classList.remove('bg-zinc-100', 'shadow-[0_0_10px_rgba(255,255,255,0.5)]');
            } else {
                progressBar.classList.remove('bg-rose-500');
            }

            const progressText = document.getElementById('progressText');
            const loadingSpinner = document.getElementById('loadingSpinner');

            const isProcessing = ['DOWNLOADING', 'ANALYZING', 'EDITING'].includes(job.status);

            if (progressText) {
                if (isProcessing) {
                    progressText.classList.remove('hidden');
                    progressText.textContent = `${job.progress_percentage}%`;
                } else {
                    progressText.classList.add('hidden');
                }
            }
            if (loadingSpinner) {
                if (isProcessing) {
                    loadingSpinner.classList.remove('hidden');
                } else {
                    loadingSpinner.classList.add('hidden');
                }
            }
            if (isProcessing) {
                progressBar.classList.add('shadow-[0_0_10px_rgba(255,255,255,0.5)]');
            } else {
                progressBar.classList.remove('shadow-[0_0_10px_rgba(255,255,255,0.5)]');
            }

            const lastLog = terminal.lastElementChild?.textContent || '';
            if (job.current_step_message && !lastLog.includes(job.current_step_message)) {
                logToTerminal(job.current_step_message, job.status === 'FAILED' ? 'error' : 'info');
            }

            // ONLY update clips DOM once when COMPLETED to avoid reloading video/DOM on every tick.
            // But we might also want to show clips if user loads a COMPLETED job from history.
            if (job.clips_json && (!window.lastRenderedJobId || window.lastRenderedJobId !== job.id || window.lastRenderedStatus !== job.status)) {
                try {
                    const clips = JSON.parse(job.clips_json);
                    const outputs = job.output_video_path ? job.output_video_path.split(',') : [];
                    const cacheBuster = job.updated_at ? new Date(job.updated_at).getTime() : Date.now();

                    let html = '';

                    if (job.status === 'COMPLETED') {
                        html += `
                        <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-5 mb-6">
                            <h3 class="text-sm font-medium text-zinc-100 mb-3">🎨 Edit Subtitle Appearance (No Re-download required)</h3>
                            <div class="flex flex-wrap gap-3 items-end">
                                <div>
                                    <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Color</label>
                                    <select id="re_subtitleColor" class="bg-zinc-950 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none">
                                        <option value="&H00FFFF" ${job.subtitle_color === '&H00FFFF' ? 'selected' : ''}>Yellow</option>
                                        <option value="&HFFFFFF" ${job.subtitle_color === '&HFFFFFF' ? 'selected' : ''}>White</option>
                                        <option value="&H00FF00" ${job.subtitle_color === '&H00FF00' ? 'selected' : ''}>Green</option>
                                        <option value="&H0000FF" ${job.subtitle_color === '&H0000FF' ? 'selected' : ''}>Red</option>
                                        <option value="&HFF0000" ${job.subtitle_color === '&HFF0000' ? 'selected' : ''}>Blue</option>
                                        <option value="&HFF00FF" ${job.subtitle_color === '&HFF00FF' ? 'selected' : ''}>Purple</option>
                                        <option value="&H00A5FF" ${job.subtitle_color === '&H00A5FF' ? 'selected' : ''}>Orange</option>
                                        <option value="&HFFFF00" ${job.subtitle_color === '&HFFFF00' ? 'selected' : ''}>Cyan</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Size</label>
                                    <select id="re_subtitleSize" class="bg-zinc-950 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none">
                                        <option value="70" ${job.subtitle_size == 70 ? 'selected' : ''}>Small</option>
                                        <option value="90" ${job.subtitle_size == 90 ? 'selected' : ''}>Medium</option>
                                        <option value="110" ${job.subtitle_size == 110 ? 'selected' : ''}>Large</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Opacity (0-100)</label>
                                    <input type="number" id="re_subtitleOpacity" value="${job.subtitle_opacity !== undefined ? job.subtitle_opacity : 100}" min="0" max="100" class="bg-zinc-950 w-20 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none">
                                </div>
                                <div class="flex items-center gap-2 mb-2 mr-2">
                                    <input type="checkbox" id="re_wordKaraoke" checked class="rounded bg-zinc-950 border-zinc-800 text-emerald-500 focus:ring-emerald-500">
                                    <span class="text-[11px] text-zinc-400 uppercase tracking-wider">Word-by-Word Karaoke</span>
                                </div>
                                <button onclick="triggerRerender()" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium py-1.5 px-4 rounded transition-colors">
                                    Apply & Re-Render
                                </button>
                            </div>
                        </div>
                        `;
                    }
                    currentClipsData = clips;
                    clips.forEach((clip, index) => {
                        const videoSrc = esc(outputs[index] || '');
                        const previewVideoSrc = videoSrc.replace('_rerender', '');

                        const tags = (clip.hashtags || []).map(t => `<span class="text-[11px] font-mono text-zinc-400 bg-zinc-800 px-2 py-1 rounded">#${esc(t.trim())}</span>`).join('');

                        html += `
                        <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col md:flex-row gap-6 mb-6 shadow-xl">
                            <div class="flex-shrink-0 w-full md:w-[260px] aspect-[9/16] bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden relative flex items-center justify-center group shadow-2xl">
                                ${previewVideoSrc ? `
                                <video id="video_${index}" src="${previewVideoSrc}?v=${cacheBuster}" class="w-full h-full object-cover" controls playsinline></video>
                                
                                <div class="absolute top-2 right-2 flex flex-col gap-1 z-20 opacity-80 hover:opacity-100 transition-opacity bg-zinc-950/80 p-1 rounded-md border border-zinc-800 backdrop-blur-sm">
                                    <button type="button" data-action="setSubPos" data-pos="top" class="text-[11px] text-amber-300 hover:text-white px-1.5 py-0.5 rounded hover:bg-zinc-800 font-mono font-bold" title="Posisi Atas">⬆️ Top</button>
                                    <button type="button" data-action="setSubPos" data-pos="middle" class="text-[11px] text-amber-300 hover:text-white px-1.5 py-0.5 rounded hover:bg-zinc-800 font-mono font-bold" title="Posisi Tengah">↔️ Mid</button>
                                    <button type="button" data-action="setSubPos" data-pos="bottom" class="text-[11px] text-amber-300 hover:text-white px-1.5 py-0.5 rounded hover:bg-zinc-800 font-mono font-bold" title="Posisi Bawah">⬇️ Bot</button>
                                </div>

                                <div id="subtitleOverlay_${index}" 
                                     data-action="startSubDrag" data-index="${index}"
                                     class="absolute bottom-[15%] left-0 w-full text-center px-2 cursor-ns-resize z-10 transition-all duration-75 select-none py-1.5 group/sub" 
                                     style="--sub-color: #FFFF00; text-shadow: 2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 0 4px 4px rgba(0,0,0,0.5); line-height: 1.3; font-size: 1.25rem;"
                                     title="🖐️ Geser/Drag ke Atas/Bawah untuk mengatur posisi Subtitle!">
                                     <div class="inline-block bg-zinc-950/80 border border-amber-400/60 text-amber-300 font-extrabold text-xs px-3 py-1.5 rounded-lg shadow-xl group-hover/sub:scale-105 transition-transform pointer-events-none">
                                         <span>💬 GESER SUBTITLE KE ATAS/BAWAH</span>
                                         <span id="posLabel_${index}" class="text-[11px] font-mono text-emerald-400 block font-semibold mt-0.5">↕️ Drag Vertikal Aktif</span>
                                     </div>
                                </div>
                                ` : `<div class="text-zinc-600 text-xs font-mono text-center px-4"><span class="animate-pulse">Processing...</span></div>`}
                            </div>
                            
                            <div class="flex-1 flex flex-col gap-4 min-w-0">
                                <div class="flex justify-between items-center bg-zinc-950/80 border border-zinc-800/80 p-3.5 rounded-lg">
                                    <div>
                                        <div class="flex items-center gap-2">
                                            <h3 class="text-base font-bold text-zinc-100">Clip ${index + 1}</h3>
                                            <span class="font-mono text-xs text-zinc-400 bg-zinc-900 border border-zinc-800 px-2.5 py-0.5 rounded">⏱️ ${esc(clip.start_time)} - ${esc(clip.end_time)}</span>
                                        </div>
                                    </div>
                                    <div class="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-3.5 py-1.5 rounded-lg font-mono text-xs text-center flex items-center gap-2">
                                        <span class="text-[11px] uppercase tracking-wider text-zinc-400 font-sans">Viral Score</span>
                                        <span class="text-xl font-extrabold text-emerald-400">${esc(clip.viral_score)}</span><span class="text-zinc-400 text-xs">/100</span>
                                    </div>
                                </div>

                                ${clip.hook_title ? `<div class="bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-semibold px-3.5 py-2 rounded-lg flex items-center gap-2"><span>🔥</span> <span>Hook Title: <strong class="text-amber-200">${esc(clip.hook_title)}</strong></span></div>` : ''}
                                
                                ${clip.viral_reasoning ? `
                                <div class="bg-indigo-950/40 border border-indigo-500/30 rounded-lg p-3 text-xs text-indigo-200 leading-relaxed shadow-sm">
                                    <div class="font-bold text-indigo-400 flex items-center gap-1.5 mb-1 text-[11px] uppercase tracking-wider">
                                        <span>💡 AI Viral Hook Rating Breakdown</span>
                                    </div>
                                    <p>${esc(clip.viral_reasoning)}</p>
                                </div>
                                ` : ''}

                                <div>
                                    <div class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1.5 font-mono">AI Context & Summary</div>
                                    <div class="text-xs text-zinc-300 bg-zinc-950/60 border border-zinc-800/80 rounded-lg p-3 leading-relaxed">${esc(clip.caption)}</div>
                                </div>
                                
                                <!-- Multi-Platform Caption Copy Bar -->
                                <div>
                                    <div class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1.5 font-mono">1-Click Platform Copy</div>
                                    <div class="grid grid-cols-3 gap-2.5">
                                        <button data-action="copyCaption" data-platform="tiktok" data-index="${index}" class="bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-200 text-xs py-2 px-3 rounded-lg transition-colors flex items-center justify-center gap-2 font-medium shadow-sm">🎵 TikTok</button>
                                        <button data-action="copyCaption" data-platform="reels" data-index="${index}" class="bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-200 text-xs py-2 px-3 rounded-lg transition-colors flex items-center justify-center gap-2 font-medium shadow-sm">📸 Reels</button>
                                        <button data-action="copyCaption" data-platform="shorts" data-index="${index}" class="bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-200 text-xs py-2 px-3 rounded-lg transition-colors flex items-center justify-center gap-2 font-medium shadow-sm">🔴 Shorts</button>
                                    </div>
                                </div>

                                <!-- Visual Timeline & Trim Editor -->
                                <div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 space-y-2">
                                    <div class="text-[11px] text-zinc-400 font-bold uppercase tracking-wider font-mono flex items-center justify-between">
                                        <span>✂️ Visual Trim & Timeline Editor</span>
                                        <span id="trimRangeLabel_${index}" class="text-amber-400 font-mono text-[11px]">${esc(clip.start_time)} ➔ ${esc(clip.end_time)}</span>
                                    </div>
                                    <div class="grid grid-cols-2 gap-2 text-xs">
                                        <div>
                                            <label class="text-[11px] text-zinc-400 block mb-0.5">Start Time (MM:SS)</label>
                                            <input type="text" id="trimStart_${index}" value="${esc(clip.start_time)}" class="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-zinc-200 font-mono text-center">
                                        </div>
                                        <div>
                                            <label class="text-[11px] text-zinc-400 block mb-0.5">End Time (MM:SS)</label>
                                            <input type="text" id="trimEnd_${index}" value="${esc(clip.end_time)}" class="w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-zinc-200 font-mono text-center">
                                        </div>
                                    </div>
                                    <button data-action="retrim" data-index="${index}" class="w-full bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 font-bold text-xs py-1.5 rounded transition flex items-center justify-center gap-1">
                                        <span>✂️ Re-Trim Clip & Re-Render</span>
                                    </button>
                                </div>

                                <!-- AI 3-Thumbnail Cover Gallery -->
                                ${clip.thumbnail_variants && clip.thumbnail_variants.length ? `
                                <div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
                                    <div class="text-[11px] text-zinc-400 font-bold uppercase tracking-wider mb-2 font-mono flex items-center justify-between">
                                        <span>🖼️ AI 3-Thumbnail Cover Gallery (9:16)</span>
                                        <span class="text-[11px] text-amber-400 font-mono uppercase">High Retention</span>
                                    </div>
                                    <div class="grid grid-cols-3 gap-2">
                                        ${clip.thumbnail_variants.map((v, vIdx) => `
                                        <div class="relative group rounded border border-zinc-800 overflow-hidden bg-zinc-900">
                                            <img src="${esc(v)}" class="w-full aspect-[9/16] object-cover">
                                            <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                                                <a href="${esc(v)}" download class="bg-amber-400 text-zinc-950 font-bold text-[11px] px-2 py-1 rounded shadow">Var ${vIdx + 1} 📥</a>
                                            </div>
                                        </div>
                                        `).join('')}
                                    </div>
                                </div>
                                ` : ''}

                                ${previewVideoSrc ? `
                                <div class="mt-auto pt-3 border-t border-zinc-800/60 flex flex-col xl:flex-row gap-3 items-center">
                                    <div class="flex gap-2 w-full xl:w-auto flex-1">
                                        <a href="${videoSrc}" download class="flex-1 bg-zinc-100 hover:bg-white text-zinc-950 font-bold text-xs py-2.5 px-3 rounded-lg text-center transition-colors flex items-center justify-center gap-1.5 shadow">📥 Download MP4</a>
                                        <a href="${videoSrc.replace('.mp4', '_cover.jpg')}" download class="flex-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-semibold text-xs py-2.5 px-3 rounded-lg text-center transition-colors flex items-center justify-center gap-1.5 border border-zinc-700">🖼️ Cover (.jpg)</a>
                                    </div>
                                    <div class="flex items-center gap-2 w-full xl:w-auto">
                                        <select id="postMode_${index}" class="bg-zinc-950 border border-zinc-800 text-zinc-200 text-xs rounded-lg py-2.5 px-3 focus:outline-none focus:border-zinc-600">
                                            <option value="inbox">📥 Mode Draft Inbox</option>
                                            <option value="direct">⚡ Mode Direct Post</option>
                                        </select>
                                        <button data-action="publishTikTok" data-src="${videoSrc}" data-index="${index}" class="bg-[#FE2C55] hover:bg-[#E6284C] text-white font-bold text-xs py-2.5 px-4 rounded-lg transition-colors whitespace-nowrap flex items-center gap-1.5 shadow-lg shadow-rose-900/20">🚀 Post to TikTok</button>
                                    </div>
                                </div>
                                ` : ''}
                            </div>
                        </div>
                        `;
                    });

                    document.getElementById('clipsContainer').innerHTML = html;

                    // Ensure listeners are only attached once per render
                    if (job.status === 'COMPLETED') {
                        ['re_subtitleColor', 're_subtitleSize', 're_subtitleOpacity', 're_wordKaraoke'].forEach(id => {
                            const el = document.getElementById(id);
                            if(el) {
                                el.removeEventListener('input', updateLivePreviewStyles); // remove old if exists
                                el.addEventListener('input', updateLivePreviewStyles);
                            }
                        });
                        updateLivePreviewStyles();
                    }
                    
                    window.lastRenderedJobId = job.id;
                    window.lastRenderedStatus = job.status;
                } catch (e) {
                    console.error("Failed to parse clips JSON", e);
                }
            }
        }
"""
    content = re.sub(updateUI_pattern, new_updateUI, content, flags=re.DOTALL)
    
    # 5. Remove parsedSRTCache and parseSRTTime and initSubtitlesDirectly
    content = re.sub(r'const parsedSRTCache = \{.*?\n            \}', '', content, flags=re.DOTALL)
    content = re.sub(r'function parseSRTTime\(.*?\}', '', content, flags=re.DOTALL)
    content = re.sub(r'function initSubtitlesDirectly\(.*?\}\);?\s*\}', '', content, flags=re.DOTALL)
    
    # 6. Change alerts to showToast in publishTikTokWithMode
    content = content.replace('alert(`🚀', 'showToast(`🚀')
    content = content.replace('alert(`🎉 SKEDULER', 'showToast(`🎉 SKEDULER')
    content = content.replace('alert(`🎉 SUKSES POSTING', 'showToast(`🎉 SUKSES POSTING')
    content = content.replace('alert(`🎉 SUKSES!', 'showToast(`🎉 SUKSES!')
    content = content.replace("alert('❌ TikTok Post Failed:\\n' + errMsg);", "showToast('❌ TikTok Post Failed: ' + errMsg);")
    content = content.replace("alert('❌ Error sending video to TikTok: ' + e.message);", "showToast('❌ Error: ' + e.message);")
    content = content.replace("alert('Judul disalin: ' + text);", "showToast('Judul disalin!');")
    
    # 7. Add ETA to Terminal & ETA parser
    # We will let ETA be handled in python script soon or just in HTML.
    # We can inject ETA into the updateUI.

    # 8. Modify History to include delete job
    history_html = '''
                        <div class="text-[11px] text-zinc-400 font-mono relative z-10 pointer-events-none">${esc(dateStr)}</div>
                        <div class="flex items-center justify-between mt-auto pt-2 border-t border-zinc-900 relative z-10 pointer-events-none">
                            <span class="text-[11px] font-mono font-medium px-2 py-0.5 rounded bg-zinc-900 ${esc(statusColor)}">${esc(job.status)}</span>
                            <span class="text-[11px] text-zinc-400 font-mono font-semibold bg-zinc-900 px-2 py-0.5 rounded">${esc(clipsCount)} Clips</span>
                        </div>
                        <div class="absolute top-2 right-2 z-20">
                            <button data-action="deleteJob" data-job-id="${esc(job.id)}" class="text-[11px] bg-rose-500/20 text-rose-400 hover:text-rose-300 hover:bg-rose-500/40 px-2 py-1 rounded" title="Delete Job">🗑️ Delete</button>
                        </div>
                    </div>
'''
    content = content.replace('''
                        <div class="text-[11px] text-zinc-400 font-mono relative z-10 pointer-events-none">${esc(dateStr)}</div>
                        <div class="flex items-center justify-between mt-auto pt-2 border-t border-zinc-900 relative z-10 pointer-events-none">
                            <span class="text-[11px] font-mono font-medium px-2 py-0.5 rounded bg-zinc-900 ${esc(statusColor)}">${esc(job.status)}</span>
                            <span class="text-[11px] text-zinc-400 font-mono font-semibold bg-zinc-900 px-2 py-0.5 rounded">${esc(clipsCount)} Clips</span>
                        </div>
                    </div>''', history_html)

    # 9. Handle delete job in global delegate
    delete_js = """
                } else if (action === 'deleteJob') {
                    if(confirm('Apakah Anda yakin ingin menghapus job ini berserta filenya?')) {
                        fetch(`/api/v1/clips/${el.dataset.jobId}`, { method: 'DELETE' })
                        .then(res => res.json())
                        .then(() => loadHistory())
                        .catch(e => showToast('Error delete: ' + e));
                    }
                }
"""
    content = content.replace("} else if (action === 'publishTikTok') {", delete_js + "\n                } else if (action === 'publishTikTok') {")
    
    # 10. Change advanced settings into Tabs.
    # Too complex for regex, I'll do this via beautifulsoup or manual replacement.
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    modify()

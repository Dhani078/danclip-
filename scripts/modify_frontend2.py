import re

def modify():
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # Define the new tabs HTML
    tabs_html = """
                    <!-- Advanced Settings (Tabs) -->
                    <div class="border border-zinc-800 rounded-md bg-zinc-950/50 mt-2">
                        <div class="flex border-b border-zinc-800">
                            <button type="button" onclick="switchSettingsTab('video')" id="tabSettingsVideo" class="flex-1 py-2 text-xs font-medium text-emerald-400 border-b-2 border-emerald-400">🎥 Video & AI</button>
                            <button type="button" onclick="switchSettingsTab('subtitle')" id="tabSettingsSubtitle" class="flex-1 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent">💬 Subtitles</button>
                            <button type="button" onclick="switchSettingsTab('branding')" id="tabSettingsBranding" class="flex-1 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent">✨ Branding</button>
                        </div>
                        
                        <div class="p-4">
                            <!-- Tab: Video -->
                            <div id="settingsVideo" class="flex flex-col gap-3">
                                <div class="grid grid-cols-2 gap-3">
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Aspect Ratio</label>
                                        <select id="aspectRatio" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                            <option value="9:16">9:16 (TikTok/Reels)</option>
                                            <option value="4:5">4:5 (Instagram)</option>
                                            <option value="1:1">1:1 (Square)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Layout Style</label>
                                        <select id="cropStyle" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                            <option value="center_crop">Auto Center Crop</option>
                                            <option value="blur_pad">Blur Background</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="grid grid-cols-2 gap-3">
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Clips to Extract</label>
                                        <select id="clipCount" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                            <option value="1">1 Clip (Faster)</option>
                                            <option value="3" selected>3 Clips (Balanced)</option>
                                            <option value="5">5 Clips (Deep Search)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Podcast Layout Mode</label>
                                        <select id="layoutMode" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                            <option value="auto" selected>🤖 Auto-Detect</option>
                                            <option value="single">👤 Single Speaker</option>
                                            <option value="split">👥 Split (Podcast)</option>
                                            <option value="gaming_header">🎮 Gaming Mode 1</option>
                                            <option value="gaming_overlay">🎮 Gaming Mode 2</option>
                                        </select>
                                    </div>
                                </div>
                                <div>
                                    <div class="flex items-center justify-between mb-1">
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider block font-semibold text-emerald-400">🤖 AI Director Prompt</label>
                                        <button type="button" onclick="openPromptModal()" class="text-[11px] text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 transition">🔍 Expand</button>
                                    </div>
                                    <textarea id="customPrompt" rows="2" placeholder="Custom instructions for Gemini AI..." class="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-zinc-200 p-2.5 focus:outline-none focus:border-emerald-500 placeholder-zinc-600 font-mono"></textarea>
                                </div>
                            </div>

                            <!-- Tab: Subtitle -->
                            <div id="settingsSubtitle" class="flex flex-col gap-3 hidden">
                                <div>
                                    <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Style Preset</label>
                                    <select id="subtitlePreset" class="w-full bg-zinc-900 border border-amber-500/30 rounded text-xs text-amber-300 font-semibold py-1.5 px-2 focus:outline-none focus:border-amber-500">
                                        <option value="hormozi" selected>🔥 Alex Hormozi (Bold Yellow)</option>
                                        <option value="mrbeast">⚡ MrBeast (Multi-Color)</option>
                                        <option value="multicolor">🎨 Auto Highlights</option>
                                        <option value="tiktok_neon">✨ TikTok Neon</option>
                                        <option value="ali_abdaal">📖 Ali Abdaal (Box)</option>
                                    </select>
                                </div>
                                <div class="grid grid-cols-2 gap-3">
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Color</label>
                                        <select id="subtitleColor" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                            <option value="&H00FFFF">Yellow</option>
                                            <option value="&HFFFFFF">White</option>
                                            <option value="&H00FF00">Green</option>
                                            <option value="&H0000FF">Red</option>
                                            <option value="&HFF0000">Blue</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Position</label>
                                        <select id="subtitlePosition" onchange="setSubtitlePos(this.value)" class="w-full bg-zinc-900 border border-emerald-500/30 rounded text-xs text-emerald-400 py-1.5 px-2 focus:outline-none focus:border-emerald-500">
                                            <option value="bottom" selected>⬇️ Bottom</option>
                                            <option value="middle">↔️ Middle</option>
                                            <option value="top">⬆️ Top</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="grid grid-cols-3 gap-3">
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Size</label>
                                        <select id="subtitleSize" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                            <option value="70">Small</option>
                                            <option value="90" selected>Medium</option>
                                            <option value="110">Large</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Opacity</label>
                                        <input type="number" id="subtitleOpacity" value="100" min="0" max="100" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                    </div>
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">Language</label>
                                        <select id="targetLanguage" class="w-full bg-zinc-900 border border-sky-500/30 rounded text-xs text-sky-400 py-1.5 px-2 focus:outline-none focus:border-sky-500">
                                            <option value="id" selected>🇮🇩 ID</option>
                                            <option value="en">🇺🇸 EN</option>
                                        </select>
                                    </div>
                                </div>
                            </div>

                            <!-- Tab: Branding -->
                            <div id="settingsBranding" class="flex flex-col gap-3 hidden">
                                <div class="grid grid-cols-2 gap-3">
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">🖼️ Custom Logo</label>
                                        <input type="file" id="watermarkFile" accept="image/*" onchange="uploadWatermarkFile(this)" class="w-full bg-zinc-900 border border-zinc-800 rounded text-[11px] text-zinc-400 py-1 px-1.5 focus:outline-none">
                                        <input type="hidden" id="watermarkPath" value="">
                                    </div>
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">📍 Logo Position</label>
                                        <select id="watermarkPosition" class="w-full bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 py-1.5 px-2 focus:outline-none focus:border-zinc-600">
                                            <option value="safe_center" selected>🟢 Safe Center</option>
                                            <option value="top_right">↗️ Top Right</option>
                                            <option value="bottom_left">↙️ Bottom Left</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="grid grid-cols-2 gap-3">
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">🔤 Custom Font (.ttf)</label>
                                        <input type="file" id="fontFile" accept=".ttf,.otf" onchange="uploadFontFile(this)" class="w-full bg-zinc-900 border border-zinc-800 rounded text-[11px] text-zinc-400 py-1 px-1.5 focus:outline-none">
                                        <input type="hidden" id="fontPath" value="">
                                    </div>
                                    <div>
                                        <label class="text-[11px] text-zinc-400 uppercase tracking-wider mb-1 block">🔔 Audio SFX</label>
                                        <label class="flex items-center gap-2 cursor-pointer mt-2">
                                            <input type="checkbox" id="enableSFX" checked class="rounded bg-zinc-900 border-zinc-800 text-zinc-100 focus:ring-0">
                                            <span class="text-xs text-amber-400 font-semibold">Play Pop on Hook</span>
                                        </label>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
"""

    pattern = r'<details class="group border border-zinc-800 rounded-md bg-zinc-950/50">.*?</details>'
    content = re.sub(pattern, tabs_html, content, flags=re.DOTALL)
    
    # Inject switchSettingsTab function
    script = """
        function switchSettingsTab(tabName) {
            ['video', 'subtitle', 'branding'].forEach(t => {
                document.getElementById('settings' + t.charAt(0).toUpperCase() + t.slice(1)).classList.add('hidden');
                let btn = document.getElementById('tabSettings' + t.charAt(0).toUpperCase() + t.slice(1));
                btn.classList.remove('text-emerald-400', 'border-emerald-400');
                btn.classList.add('text-zinc-400', 'border-transparent');
            });
            document.getElementById('settings' + tabName.charAt(0).toUpperCase() + tabName.slice(1)).classList.remove('hidden');
            let activeBtn = document.getElementById('tabSettings' + tabName.charAt(0).toUpperCase() + tabName.slice(1));
            activeBtn.classList.remove('text-zinc-400', 'border-transparent');
            activeBtn.classList.add('text-emerald-400', 'border-emerald-400');
        }
"""
    content = content.replace("function loadHistory() {", script + "\n        function loadHistory() {")
    
    # Add a limit batch check to submit event listener (in DOMContentLoaded or directly where it is handled)
    # The form submit is inside `btnSubmit.addEventListener` or similar. Let's find btnSubmit.
    content = content.replace(
        "const urls = document.getElementById('url').value.split('\\n').map(u => u.trim()).filter(u => u);",
        """const urls = document.getElementById('url').value.split('\\n').map(u => u.trim()).filter(u => u);
            if (urls.length > 5) {
                showToast("⚠️ Maximal 5 URL dalam satu batch!");
                return;
            }"""
    )
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    modify()

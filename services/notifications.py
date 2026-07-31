import httpx
import os
import json

async def send_webhook_notification(
    webhook_url: str,
    job_id: str,
    video_title: str,
    clips_data: list,
    server_base_url: str = "http://localhost:8000"
) -> dict:
    """
    Sends multi-platform webhook notifications (Discord, Slack, Zapier, Make.com, Telegram)
    when video processing completes, providing direct clip download links & viral scores.
    """
    if not webhook_url:
        return {"status": "skipped", "message": "No webhook URL provided"}
        
    # Check if user passed Telegram Bot Token & Chat ID format (e.g. tg:BOT_TOKEN:CHAT_ID)
    if webhook_url.startswith("tg:") or "api.telegram.org" in webhook_url:
        try:
            if webhook_url.startswith("tg:"):
                parts = webhook_url.split(":")
                bot_token = f"{parts[1]}:{parts[2]}"
                chat_id = parts[3]
            else:
                # Format: https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>
                bot_token = webhook_url.split("/bot")[1].split("/")[0]
                chat_id = webhook_url.split("chat_id=")[1].split("&")[0]
            return await send_telegram_notification(bot_token, chat_id, video_title, clips_data, server_base_url)
        except Exception as e:
            print(f"[Telegram Parse Error] {e}")

    try:
        # Build rich Discord embed payload
        embeds = []
        for i, clip in enumerate(clips_data):
            clip_id = clip.get("id", f"clip_{i+1}")
            viral_score = clip.get("viral_score", 90)
            hook_title = clip.get("hook_title", "Viral Clip")
            tiktok_cap = clip.get("tiktok_caption", clip.get("caption", ""))
            
            video_url = f"{server_base_url}/exports/{job_id}_{clip_id}.mp4"
            cover_url = f"{server_base_url}/exports/{job_id}_{clip_id}_cover.jpg"
            
            embeds.append({
                "title": f"🎬 Clip #{i+1}: {hook_title}",
                "description": f"**Viral Score:** 🔥 `{viral_score}/100`\n\n**TikTok Caption:**\n```{tiktok_cap[:200]}...```",
                "color": 16738560 if viral_score > 90 else 5814783,
                "fields": [
                    {"name": "📥 Video Download", "value": f"[Download MP4]({video_url})", "inline": True},
                    {"name": "🖼️ Cover Image", "value": f"[Download JPG]({cover_url})", "inline": True}
                ],
                "image": {"url": cover_url} if i == 0 else {}
            })

        payload = {
            "username": "AutoClip AI Engine 🤖",
            "content": f"🚀 **New Auto-Clipped Clips Ready for Upload!**\n**Source Video:** `{video_title}`\n**Job ID:** `{job_id}`",
            "embeds": embeds[:4] # Discord supports max 10 embeds, limit to 4
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code in [200, 204]:
                print(f"[Notification Engine] Sent Webhook successfully to: {webhook_url}")
                return {"status": "success", "http_code": resp.status_code}
            else:
                print(f"[Notification Engine Warning] Webhook responded with status: {resp.status_code}")
                return {"status": "error", "http_code": resp.status_code, "response": resp.text}
                
    except Exception as e:
        print(f"[Notification Engine Error] {e}")
        return {"status": "failed", "error": str(e)}

async def send_telegram_notification(
    bot_token: str,
    chat_id: str,
    video_title: str,
    clips_data: list,
    server_base_url: str = "http://localhost:8000"
) -> dict:
    """
    Sends notification via Telegram Bot API with direct download links.
    """
    if not bot_token or not chat_id:
        return {"status": "skipped", "message": "Telegram credentials not provided"}
        
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        from datetime import datetime, timedelta
        now = datetime.now()
        
        msg = f"🚀 *AutoClip AI Render Selesai!*\n\n"
        msg += f"📹 *Video:* `{video_title}`\n"
        msg += f"⏰ *Jadwal Anti-Spam Posting (Interval 3 Jam):*\n\n"
        
        inline_keyboard = []
        for i, clip in enumerate(clips_data):
            clip_id = clip.get("id", f"clip_{i+1}")
            score = clip.get("viral_score", 90)
            hook = clip.get("hook_title", "Viral Clip")
            job_id_val = clip.get("job_id", "job")
            download_link = f"{server_base_url}/exports/{job_id_val}_{clip_id}.mp4"
            cover_link = f"{server_base_url}/exports/{job_id_val}_{clip_id}_cover.jpg"
            sched_time = (now + timedelta(hours=i * 3)).strftime("%H:%M WIB")
            
            msg += f"📌 *Klip {i+1}* (🔥 Score: {score}/100) — *Jadwal: {sched_time}*\n"
            msg += f"🎬 *{hook}*\n"
            msg += f"📥 [Download MP4]({download_link}) | 🖼️ [Download Cover]({cover_link})\n\n"
            
            # Interactive Telegram buttons to trigger TikTok upload straight from Telegram chat
            inline_keyboard.append([
                {"text": f"🚀 Post Klip #{i+1} ke TikTok (Draft)", "callback_data": f"tt_inbox:{job_id_val}:{clip_id}"},
                {"text": f"⚡ Post Klip #{i+1} Direct Live", "callback_data": f"tt_direct:{job_id_val}:{clip_id}"}
            ])
            
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
            "reply_markup": {"inline_keyboard": inline_keyboard}
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return {"status": "success" if resp.status_code == 200 else "error", "response": resp.text}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

async def send_failure_notification(
    webhook_url: str,
    job_id: str,
    error_msg: str
) -> dict:
    if not webhook_url:
        return {"status": "skipped", "message": "No webhook URL provided"}
        
    msg = f"❌ *AutoClip AI Render Gagal!*\n\n"
    msg += f"🆔 *Job ID:* `{job_id}`\n"
    msg += f"⚠️ *Error:* `{error_msg[:300]}`"
    
    if webhook_url.startswith("tg:") or "api.telegram.org" in webhook_url:
        try:
            if webhook_url.startswith("tg:"):
                parts = webhook_url.split(":")
                bot_token = f"{parts[1]}:{parts[2]}"
                chat_id = parts[3]
            else:
                bot_token = webhook_url.split("/bot")[1].split("/")[0]
                chat_id = webhook_url.split("chat_id=")[1].split("&")[0]
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload)
        except Exception as e:
            print(f"[Telegram Failure Notify Error] {e}")
    else:
        try:
            payload = {"content": f"❌ **AutoClip AI Render Gagal!**\n**Job ID:** `{job_id}`\n**Error:** `{error_msg[:300]}`"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(webhook_url, json=payload)
        except Exception as e:
            print(f"[Webhook Failure Notify Error] {e}")

async def send_tiktok_publish_telegram_notification(
    webhook_url: str,
    title: str,
    caption: str,
    mode: str,
    publish_id: str = ""
) -> dict:
    from config import settings
    target_webhook = (webhook_url or "").strip() or settings.DEFAULT_WEBHOOK_URL
    if not target_webhook:
        return {"status": "skipped", "message": "No webhook URL configured"}
        
    mode_text = "📥 TikTok Draft Inbox" if mode == "inbox" else ("⚡ TikTok Direct Post" if mode == "direct" else "⏰ TikTok Scheduled Post")
    
    msg = f"🎵 *AutoClip TikTok Publish Notification*\n\n"
    msg += f"📌 *Mode:* `{mode_text}`\n"
    if title:
        msg += f"🎬 *Judul/Hook:* `{title[:120]}`\n"
    if publish_id:
        msg += f"🆔 *Publish ID:* `{publish_id}`\n"
    
    if caption:
        msg += f"\n📝 *Caption & Hashtag AI TikTok:*\n"
        msg += f"```\n{caption[:1000]}\n```\n"
        msg += f"💡 _Tip: Tap/tekan kotak caption di atas di Telegram HP untuk menyalin langsung!_\n"
    
    if target_webhook.startswith("tg:") or "api.telegram.org" in target_webhook:
        try:
            if target_webhook.startswith("tg:"):
                parts = target_webhook.split(":")
                bot_token = f"{parts[1]}:{parts[2]}"
                chat_id = parts[3]
            else:
                bot_token = target_webhook.split("/bot")[1].split("/")[0]
                chat_id = target_webhook.split("chat_id=")[1].split("&")[0]
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                return {"status": "success" if resp.status_code == 200 else "error", "response": resp.text}
        except Exception as e:
            print(f"[TikTok Telegram Notify Error] {e}")
            return {"status": "failed", "error": str(e)}
    else:
        try:
            payload = {"content": f"🎵 **AutoClip TikTok Publish:** {mode_text}\n**Title:** {title}\n**Caption:**\n```{caption[:1000]}```"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(target_webhook, json=payload)
                return {"status": "success" if resp.status_code in [200, 204] else "error"}
        except Exception as e:
            print(f"[TikTok Webhook Notify Error] {e}")
            return {"status": "failed", "error": str(e)}

async def start_telegram_bot_listener(bot_token: str = "8870492783:AAFLR7nuio7faUpiuwLhLeQK4VY1EV1q9_o"):
    """
    Long-polling loop for Telegram Bot callback queries.
    Allows user to click 'Post to TikTok' buttons directly inside Telegram chat!
    """
    import asyncio, json, os
    if not bot_token:
        return
        
    offset = 0
    print("[Telegram Bot Listener] 🚀 Telegram Bot Listener started for 1-Click Telegram TikTok buttons...")
    
    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=20"
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        if "callback_query" in update:
                            cb = update["callback_query"]
                            cb_id = cb["id"]
                            cb_data = cb.get("data", "")
                            chat_id = cb["message"]["chat"]["id"]
                            
                            if cb_data.startswith("tt_inbox:") or cb_data.startswith("tt_direct:"):
                                parts = cb_data.split(":")
                                mode = "inbox" if parts[0] == "tt_inbox" else "direct"
                                jid = parts[1]
                                cid = parts[2]
                                
                                # Acknowledge button click in Telegram UI
                                await client.post(
                                    f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                                    json={"callback_query_id": cb_id, "text": f"⏳ Mengunggah Klip #{cid} ke TikTok ({mode.upper()})...", "show_alert": False}
                                )
                                
                                # Query database for clip details & publish
                                try:
                                    from database import AsyncSessionLocal
                                    from models import VideoJob
                                    from services.tiktok_publisher import publish_video_to_tiktok
                                    from config import settings
                                    
                                    async with AsyncSessionLocal() as session:
                                        job = await session.get(VideoJob, jid)
                                        if job and job.clips_json:
                                            clips = json.loads(job.clips_json)
                                            target_clip = next((c for c in clips if c.get("id") == cid), None)
                                            if target_clip:
                                                video_file = os.path.join(settings.STORAGE_DIR, "exports", f"{jid}_{cid}.mp4")
                                                caption = target_clip.get("tiktok_caption") or target_clip.get("caption") or target_clip.get("hook_title", "")
                                                
                                                res = await publish_video_to_tiktok(
                                                    video_file,
                                                    access_token=settings.TIKTOK_ACCESS_TOKEN,
                                                    title=caption,
                                                    privacy_level="PUBLIC_TO_EVERYONE" if mode == "direct" else "SELF_ONLY",
                                                    post_mode=mode
                                                )
                                                
                                                # Auto fallback to inbox if Sandbox rejects Direct Post
                                                if res.get("status") == "error" and mode == "direct":
                                                    res = await publish_video_to_tiktok(
                                                        video_file,
                                                        access_token=settings.TIKTOK_ACCESS_TOKEN,
                                                        title=caption,
                                                        privacy_level="SELF_ONLY",
                                                        post_mode="inbox"
                                                    )
                                                    mode = "inbox (Fallback Sandbox)"

                                                if res.get("status") == "success":
                                                    pub_id = res.get("publish_id", "N/A")
                                                    mode_label = "📥 Draft Inbox" if "inbox" in mode else "⚡ Direct Live Feed"
                                                    success_text = f"🎉 *BERHASIL MENGUNGGAH KE TIKTOK!*\n\n"
                                                    success_text += f"📌 *Mode:* `{mode_label}`\n"
                                                    success_text += f"🆔 *Publish ID:* `{pub_id}`\n\n"
                                                    success_text += f"📝 *Caption & Hashtag:*\n```\n{caption[:500]}\n```"
                                                    
                                                    await client.post(
                                                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                                        json={"chat_id": chat_id, "text": success_text, "parse_mode": "Markdown"}
                                                    )
                                                else:
                                                    err_msg = res.get("message", "Unknown error")
                                                    await client.post(
                                                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                                        json={"chat_id": chat_id, "text": f"❌ *Gagal Posting TikTok:* {err_msg}", "parse_mode": "Markdown"}
                                                    )
                                except Exception as upload_err:
                                    await client.post(
                                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                        json={"chat_id": chat_id, "text": f"❌ *Error Publisher:* {str(upload_err)}", "parse_mode": "Markdown"}
                                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Telegram Listener Warning] {e}")
                await asyncio.sleep(5)




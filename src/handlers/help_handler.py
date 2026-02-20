"""
Topluluk yardımlaşma komut handler'ları.
"""

import asyncio
from slack_bolt import App
from src.core.logger import logger
from src.core.settings import get_settings
from src.core.rate_limiter import get_rate_limiter
from src.core.validators import HelpRequest
from src.commands import ChatManager
from src.services import HelpService
from src.repositories import UserRepository


def setup_help_handlers(
    app: App,
    help_service: HelpService,
    chat_manager: ChatManager,
    user_repo: UserRepository
):
    """Yardımlaşma handler'larını kaydeder."""
    settings = get_settings()
    rate_limiter = get_rate_limiter(
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window
    )
    
    @app.command("/yardim-iste")
    def handle_help_request(ack, body):
        """Yardım isteği oluşturur."""
        ack()
        user_id = body["user_id"]
        channel_id = body["channel_id"]
        text = body.get("text", "").strip()
        
        # Rate limiting kontrolü
        allowed, error_msg = rate_limiter.is_allowed(user_id)
        if not allowed:
            chat_manager.post_ephemeral(channel=channel_id, user=user_id, text=error_msg)
            return
        
        # Kullanıcı bilgisini al
        try:
            user_data = user_repo.get_by_slack_id(user_id)
            user_name = user_data.get('full_name', user_id) if user_data else user_id
        except Exception:
            user_name = user_id
        
        logger.info(f"[>] /yardim-iste komutu geldi | Kullanıcı: {user_name} ({user_id}) | Kanal: {channel_id}")
        
        # Input validation
        if not text:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text="🤔 Yardım isteği için en azından konu gerekli.\nÖrnek: `/yardim-iste Python Flask ile REST API nasıl yapılır?`"
            )
            return
        
        try:
            help_request = HelpRequest.parse_from_text(text)
        except ValueError as ve:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=f"Yardım isteği formatı hatalı. Lütfen tekrar deneyin.\n\nHata: {str(ve)}"
            )
            return
        
        # Async işlemi sync wrapper ile çalıştır
        async def process_help_request():
            try:
                help_id = await help_service.create_help_request(
                    requester_id=user_id,
                    channel_id=channel_id,
                    topic=help_request.topic,
                    description=help_request.description
                )
                
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text="✅ Yardım isteğiniz paylaşıldı! Topluluk üyeleri size yardım edebilir."
                )
                
                logger.info(f"[+] Yardım isteği oluşturuldu | Kullanıcı: {user_name} ({user_id}) | ID: {help_id}")
                
            except Exception as e:
                logger.error(f"[X] Yardım isteği hatası: {e}", exc_info=True)
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text="Yardım isteği oluşturulurken bir hata oluştu. Lütfen tekrar deneyin."
                )
        
        asyncio.run(process_help_request())
    
    @app.action("help_join_channel")
    def handle_help_join_channel(ack, body):
        """'Kanala Katıl' butonuna tıklama (pop-up)."""
        ack()
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        help_id = body["actions"][0]["value"]
        
        # Kullanıcı bilgisini al
        try:
            user_data = user_repo.get_by_slack_id(user_id)
            user_name = user_data.get('full_name', user_id) if user_data else user_id
        except Exception:
            user_name = user_id
        
        logger.info(f"[>] Kanala katılma isteği | Kullanıcı: {user_name} ({user_id}) | Yardım ID: {help_id}")
        
        # Async işlemi sync wrapper ile çalıştır
        async def process_join_channel():
            try:
                result = await help_service.join_help_channel(help_id, user_id)
                
                if result["success"]:
                    # Ephemeral mesaj (pop-up - sadece tıklayan görür)
                    chat_manager.post_ephemeral(
                        channel=channel_id,
                        user=user_id,
                        text=result["message"]
                    )
                    logger.info(f"[+] Kanala katılma başarılı | Kullanıcı: {user_name} ({user_id}) | Yardım ID: {help_id}")
                else:
                    chat_manager.post_ephemeral(
                        channel=channel_id,
                        user=user_id,
                        text=result["message"]
                    )
                    logger.warning(f"[!] Kanala katılma başarısız | Kullanıcı: {user_name} ({user_id}) | Sebep: {result.get('message')}")
                    
            except Exception as e:
                logger.error(f"[X] Kanala katılma hatası: {e}", exc_info=True)
                chat_manager.post_ephemeral(
                    channel=channel_id,
                    user=user_id,
                    text="Kanala katılırken bir hata oluştu. Lütfen tekrar deneyin."
                )
        
        asyncio.run(process_join_channel())
    
    @app.command("/help")
    def handle_help_command(ack, body):
        """Tüm mevcut komutları kategorize ederek gösterir."""
        ack()
        user_id = body["user_id"]
        channel_id = body["channel_id"]
        
        logger.info(f"[>] /help komutu kullanıldı | Kullanıcı: {user_id} | Kanal: {channel_id}")
        
        help_text = (
            "🤖 *Cemil Bot - Komut Rehberi*\n\n"
            
            "👥 *Sosyal & Etkileşim*\n"
            "• `/kahve` - Rastgele bir topluluk üyesiyle kahve sohbeti eşleşmesi\n"
            "• `/yardim-iste` - Topluluktan teknik yardım iste (otomatik kanal oluşturur)\n"
            "• `/oylama` - Topluluk oylaması başlat\n"
            "• `/daily` - Günlük topluluk sorusu gönder (Admin)\n\n"
            
            "🎓 *Eğitim & Öğrenme*\n"
            "• `/sor` - Bilgi Küpü'ne soru sor (RAG destekli Türkçe AI)\n"
            "• `/cemil-indeksle` - Bilgi Küpü'ne yeni döküman indeksle (Admin)\n\n"
            
            "🏆 *Challenge Sistemi*\n"
            "• `/challenge start <takım_sayısı>` - Yeni challenge başlat (Admin)\n"
            "• `/challenge join [challenge_id]` - Challenge'a katıl\n"
            "• `/challenge status` - Aktif challenge durumunu görüntüle\n"
            "• `/challenge bitir` - Challenge'ı tamamla ve değerlendirme başlat\n"
            "• `/challenge register` - Mevcut kanalı challenge olarak kaydet\n"
            "• `/challenge set True/False` - Değerlendirmede oy ver\n"
            "• `/challenge set github <link>` - Değerlendirmede GitHub repo ekle\n"
            "• `/challenge force [success|fail]` - Değerlendirmeyi zorla bitir (Admin)\n\n"
            
            "👤 *Profil & Geri Bildirim*\n"
            "• `/profilim` - Sistemdeki bilgilerinizi görüntüle\n"
            "• `/geri-bildirim` - Bot hakkında geri bildirim paylaş\n\n"
            
            "📊 *Yönetim & İstatistik* (Admin)\n"
            "• `/admin-istatistik` - Bot kullanım istatistikleri\n"
            "• `/admin-basarili-projeler` - Başarılı challenge projelerini listele\n\n"
            
            "🏥 *Sistem*\n"
            "• `/cemil-health` - Bot sağlık kontrolü\n\n"
            
            "💡 *İpuçları:*\n"
            "• Challenge'lar takım çalışması ve öğrenme odaklıdır\n"
            "• Yardım ve kahve kanalları otomatik kapanır, özetler DM'inize gelir\n"
            "• Bilgi Küpü sadece Türkçe cevap verir\n\n"
            
            "Sorularınız için bana `/geri-bildirim` ile ulaşabilirsiniz! 🚀"
        )
        
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text=help_text
        )
        
        logger.info(f"[+] /help komutu başarıyla işlendi | Kullanıcı: {user_id}")
    
    @app.action("help_details")
    def handle_help_details(ack, body):
        """'Detaylar' butonuna tıklama."""
        ack()
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        help_id = body["actions"][0]["value"]
        
        help_request = help_service.get_help_details(help_id)
        if not help_request:
            chat_manager.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text="❌ Yardım isteği bulunamadı."
            )
            return
        
        # Durum metni
        status_text = {
            "open": "🟢 Açık",
            "in_progress": "🟡 Devam ediyor",
            "resolved": "✅ Çözüldü",
            "closed": "🔴 Kapatıldı"
        }.get(help_request.get("status", "open"), "❓ Bilinmiyor")
        
        # Detaylı bilgi göster
        details_text = (
            f"*📋 Yardım İsteği Detayları*\n\n"
            f"*Konu:* {help_request['topic']}\n"
            f"*Açıklama:* {help_request['description']}\n"
            f"*Durum:* {status_text}\n"
            f"*Oluşturulma:* {help_request.get('created_at', 'Bilinmiyor')}\n"
        )
        
        if help_request.get('helper_id'):
            details_text += f"*Yardım Eden:* <@{help_request['helper_id']}>\n"
        
        if help_request.get('resolved_at'):
            details_text += f"*Çözülme:* {help_request['resolved_at']}\n"
        
        chat_manager.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text=details_text
        )
        
        logger.info(f"[i] Yardım detayları görüntülendi | Kullanıcı: {user_id} | Yardım ID: {help_id}")

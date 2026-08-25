# Google Yorum → Instagram Hikaye Botu

Google İşletme Profili'ne yeni bir yorum geldiğinde otomatik olarak:
1. `assets/story-templates/` klasöründeki hazır görsel/video havuzundan
   SIRADAKİ dosyayı seçer (1. yorumda 1. şablon, 2. yorumda 2. şablon...
   havuz biterse başa sarar)
2. Onu Instagram hikayesine olduğu gibi paylaşır

Tamamen **GitHub Actions** üzerinde, bulutta çalışır — kimsenin bilgisayarı
açık olmak zorunda değil, ve ücretsizdir. Google tarafında hiçbir Cloud
projesi, kart ya da onay beklemeden çalışır (bkz. "Neden Gmail?" aşağıda).

## Nasıl çalışıyor (kısaca)

Her 15 dakikada bir GitHub, bu depoda `automation/main.py` dosyasını
otomatik çalıştırır. Script sırasıyla: Google'ın yeni yorum geldiğinde
gönderdiği bildirim e-postalarını Gmail'den tarar → daha önce işlenmemiş
(state.json'da kayıtlı olmayan) olanları bulur → şablon havuzundan sırada
hangi görsel/video varsa onu alır → deponun kendi
`assets/story-templates/` klasöründeki o dosyanın herkese açık
raw.githubusercontent.com linkini üretir → o linki Instagram'a vererek
hikaye olarak yayınlar → sırayı ve işlenen mail ID'lerini
`automation/state.json` dosyasına kaydeder (bir sonraki çalıştırma nereden
devam edeceğini böyle bilir).

Ayrı bir sunucuya, veritabanına ya da ücretli bir servise ihtiyaç yok.

### Neden Gmail, Google Business Profile API değil?

Google, yorumları yönetme API'sine (Business Profile API) erişimi elle
onay gerektiren, çoğu zaman uzun süren ya da hiç sonuçlanmayan bir sürece
bağlamış durumda — üstelik bazı projelerde kart/faturalandırma da
isteyebiliyor. Bunun yerine, Google'ın zaten gönderdiği "X, İşletme için
yorum yaptı" bildirim e-postasını okuyoruz. Bunun için Google Cloud'a hiç
girmiyoruz, sadece Gmail'e bir "Uygulama Şifresi" ile bağlanıyoruz —
onay yok, kart yok, süre sınırı yok.

**Tek eksik:** bu yöntemle Google yorumuna otomatik yanıt YAZAMIYORUZ (o
hâlâ kısıtlı API'yi gerektiriyor). Google'a teşekkür yanıtını uygulamadan
elle yazman gerekiyor — Instagram paylaşımı bundan etkilenmiyor.

## Yerelde test etmek (Windows)

Tüm kurulum bilgileri (aşağıdaki secrets) elinde olduğunda, botu asıl
çalışacağı yer olan GitHub Actions'a göndermeden önce kendi bilgisayarında
denemek istersen:

1. `.env.example` dosyasını kopyalayıp adını `.env` yap, içindeki tüm
   değerleri doldur (bunlar aşağıdaki "GitHub'a secrets ekle" adımındaki
   değerlerin birebir aynısı).
2. **`başlat.bat`** dosyasına çift tıkla. Bu dosya sırasıyla: bir sanal
   ortam (.venv) oluşturur, `requirements.txt`'deki tüm kütüphaneleri
   kurar, `.env` dosyasındaki ayarları yükler ve botu bir kez çalıştırır.
   İleride `requirements.txt`'ye yeni bir kütüphane eklenirse
   (ben ekledikçe ekleyeceğim) `başlat.bat`'ı değiştirmene gerek yok —
   her çalıştırdığında dosyayı yeniden okuyup eksik olanı otomatik kurar.

Not: `raw_url_for` adımı (Instagram'a vereceğimiz linki üretmek) bu
klasörün gerçekten GitHub'a push edilmiş bir git deposu olmasını
gerektiriyor — yani tam uçtan uca bir test için önce depoyu GitHub'a
yükleyip `git clone` ile kendi bilgisayarına indirmiş olman gerekiyor,
sıfırdan indirilen bu zip klasörü üzerinde değil.

## Kurulum — sırayla yapman gerekenler

### 0) Depoyu GitHub'a yükle

Bu klasörü kendi GitHub hesabında yeni bir repo olarak oluştur (private
kalabilir). Sonraki adımlardaki "secrets" o reponun ayarlarına eklenecek.

### 1) Gmail'de Uygulama Şifresi oluştur

1. Yorum bildirimlerinin geldiği Gmail hesabında **2 Adımlı Doğrulama**
   (2FA) açık olmalı — kapalıysa myaccount.google.com/security'den aç.
2. myaccount.google.com/apppasswords adresine git, bir isim ver (örn.
   "review-bot") ve oluştur. Sana **16 haneli bir şifre** verecek — bu
   senin normal Gmail şifren DEĞİL, sadece bu bot için üretilmiş özel bir
   anahtar. Bunu not al, `GMAIL_APP_PASSWORD` olarak kullanacağız.
3. Google Business Profile uygulamasında (ya da business.google.com'da)
   **Ayarlar > Bildirimler**'den "Müşteri yorumları" e-posta bildiriminin
   açık olduğundan emin ol.
4. Bu Gmail hesabı birden fazla işletmeyi yönetiyorsa (senin durumun gibi),
   hangi işletmenin yorumlarının bu bota gideceğini `REVIEW_SOURCE_BUSINESS_NAME`
   ile belirteceğiz (aşağıda) — Google Business Profil listesindeki tam
   işletme adını not al.

### 2) Instagram / Meta tarafı

Gerekenler: Instagram hesabının **Business veya Creator** hesap olması ve
bir **Facebook Sayfasına bağlı** olması (Instagram uygulaması > Ayarlar >
Hesap Merkezi'nden kontrol edilir / bağlanır — ücretsiz, birkaç tıkla).

1. https://developers.facebook.com adresinde bir hesap aç, "My Apps >
   Create App" ile yeni bir uygulama oluştur, tür olarak "Business" seç.
2. Uygulamana **Instagram Graph API** ürününü ekle.
3. Meta Business Suite (business.facebook.com) üzerinden uygulamanı,
   ilgili Facebook Sayfasını ve Instagram hesabını birbirine bağla, ve
   uygulamana `instagram_basic`, `instagram_content_publish`,
   `pages_show_list` izinlerini ver.
4. Graph API Explorer'dan (veya Business Suite'in "System User" akışından)
   bu izinlere sahip bir **uzun ömürlü (long-lived) access token**
   üret — bu token'lar genelde 60 gün geçerli olur, süre dolmadan
   yenilemen gerekecek (System User token'ları hiç süresi dolmayacak
   şekilde de üretilebilir, mümkünse onu tercih et).
5. Instagram Business hesabının **IG User ID**'sini bulmak için:
   ```
   curl "https://graph.facebook.com/v21.0/me/accounts?access_token=<TOKEN>"
   ```
   ile Sayfa id'ni bul, sonra:
   ```
   curl "https://graph.facebook.com/v21.0/<PAGE_ID>?fields=instagram_business_account&access_token=<TOKEN>"
   ```
   ile `instagram_business_account.id` değerini al — bu senin `IG_USER_ID`'n.

### 3) Hikaye şablonlarını (görsel/video havuzu) ekle

`assets/story-templates/` klasöründe şu an 2 örnek görsel var
(`01.jpg`, `02.jpg`). Sana göndereceğim/senin ekleyeceğin diğer görselleri
de aynı klasöre, **iki haneli sıra numarasıyla** ekle:

```
assets/story-templates/
  01.jpg
  02.jpg
  03.jpg
  ...
  12.mp4   <- video da olabilir
```

Numaralandırma önemli: bot dosyaları isme göre sıralıyor, "10.jpg"nin
"2.jpg"den sonra gelmesi için iki haneli yazman gerekiyor (01, 02, ... 12).
Bot bu sırayla, yorum geldikçe birer birer paylaşır; 12. şablon da
paylaşıldıktan sonra bir sonraki yorumda tekrar 01'e döner.

Video eklersen: Instagram hikayeleri için MP4 (H.264 video / AAC ses),
dikey (9:16) format ve en fazla ~60 saniye öneriliyor — daha uzun ya da
uyumsuz formattaki videoları Instagram reddedebilir.

Görseller/videolar **olduğu gibi** paylaşılıyor, üzerlerine otomatik bir
isim/metin yazılmıyor (bunu istersen ayrıca söyle, `automation/image_gen.py`
içinde hazır bir alt yapı var, sadece devreye sokmamız gerekir).

### 4) GitHub'a secrets ve variables ekle

Repo sayfanda **Settings > Secrets and variables > Actions**'a git.

**Secrets** (gizli — "New repository secret"):
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `IG_ACCESS_TOKEN`
- `IG_USER_ID`

**Variables** ("Variables" sekmesi — "New repository variable", gizli
değil ama bir Gmail birden fazla işletme yönetiyorsa önemli):
- `REVIEW_SOURCE_BUSINESS_NAME` → Google Business Profile'daki tam
  işletme adı, örn. `Niğde Gezi Otobüsü`
- `GOOGLE_MAPS_URL` → işletmenin Google Haritalar linki (opsiyonel ama
  önerilir — aşağıdaki "Google Haritalar taraması" bölümüne bak)

### 4.1) Google Haritalar taraması (opsiyonel, önerilir)

Gmail bildirim maili bazen geç gelebiliyor (hatta bazı hesaplarda hiç
gelmeyebiliyor). Bunu aşmak için bot, ek olarak işletmenin Google
Haritalar sayfasını da doğrudan tarayıp yeni yorumları okuyabiliyor —
mail beklemeden. Bunun için `GOOGLE_MAPS_URL` değişkenine işletmenin
Haritalar linkini eklemen yeterli (Google Haritalar'da işletmeyi aç,
"Paylaş" ile linki al).

Bu resmi bir Google API'si DEĞİL, gerçek bir tarayıcı açıp (Playwright)
sayfayı okuyor — kart/onay gerektirmiyor ama Google sayfa tasarımını
değiştirirse (nadiren olur) bu kısım bozulabilir. Böyle bir durumda
Actions loglarında `[maps_watch]` ile başlayan satırları bana gösterirsen
düzeltiriz. `GOOGLE_MAPS_URL` boş bırakılırsa bu adım tamamen atlanır,
sadece Gmail yoluyla devam eder — yani bu opsiyonel bir ek güvence,
Gmail yolunun yerini almıyor, ikisi birlikte çalışıyor.

### 5) Test et

Repo sayfanda **Actions** sekmesine git, "Google Yorum -> Instagram Hikaye
Botu" workflow'unu seç, sağ üstten **"Run workflow"** ile elle bir kere
tetikle. Loglardan neyin olup neyin olmadığını görebilirsin. Sorunsuz
çalıştıysa artık otomatik olarak 15 dakikada bir kendiliğinden çalışacak.

En hızlı test: birine "dene" diye bir Google yorumu bıraktır, birkaç
dakika içinde Instagram hikayesinde görünmeli.

## Özelleştirme

- `automation/config.py` içindeki `MIN_RATING_TO_POST`,
  `MAX_REVIEWS_PER_RUN` değerlerini ihtiyacına göre değiştirebilirsin.
- Sırayı sıfırlamak (baştan başlatmak) istersen `automation/state.json`
  dosyasını depodan silmen veya içindeki `next_template_index`'i `0`
  yapman yeterli.
- Varsayılan olarak sadece **4 ve 5 yıldızlı** yorumlar hikayeye
  paylaşılıyor (marka güvenliği için); daha düşük puanlı ya da puanı
  maildeki metinden okunamayan yorumlar hikayeye atılmıyor, sadece
  "işlendi" olarak işaretleniyor. Bunu `MIN_RATING_TO_POST` ile
  değiştirebilirsin.

## Bilinmesi gerekenler

- **Erişim anahtarları GitHub Secrets'ta şifreli saklanır** — repo
  sahipleri bile bunları tekrar okuyamaz, sadece workflow çalışırken
  kullanılır. Yine de repoyu ve bu secrets'lara kimin erişimi olduğunu
  kontrol altında tut.
- **Google'a teşekkür yanıtı elle yazılıyor** — bu akış otomatik yanıt
  yazmıyor (yukarıdaki "Neden Gmail?" bölümüne bak), Instagram tarafı
  bundan etkilenmiyor.
- **Bildirim maili Spam'e düşebilir** — bir kere "Spam değil" olarak
  işaretledikten sonra Gmail genelde öğreniyor, ama arada bir Spam
  klasörünü kontrol etmekte fayda var; oraya düşen mailleri bot görmez.
- **Instagram token'ı süreli** — long-lived token genelde 60 günde bir
  yenilenmesi gerekiyor (System User token kullanırsan bu dertten
  kurtulursun). Süresi dolarsa bot Instagram'a paylaşamaz hale gelir,
  hatayı Actions loglarından görürsün.
- **Depo boyutu neredeyse hiç büyümüyor** — şablonları bir kere
  ekliyorsun, her paylaşımda sadece küçük bir `state.json` dosyası
  güncelleniyor (görsel/video tekrar tekrar commit edilmiyor).
- **GitHub Actions dakika limiti** — private repolarda ayda 2000 dakika
  ücretsiz (bu bot çok az kullanır, sorun olmaz); public repo yaparsan
  limit tamamen kalkar.
- **Zamanlama tam 15 dakikada bir garanti değil** — GitHub yoğunlukta
  birkaç dakika gecikmeli tetikleyebilir, bu normaldir.

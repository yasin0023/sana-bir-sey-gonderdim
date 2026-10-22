# BIST Sanal Trader (v0.2)

Telefon tarayıcısından erişilebilen Streamlit prototipi: BIST hisse izleme, günlük fiyat geçmişi, SMA/RSI sinyalleri ve sanal portföy.

## Güvenlik ve dürüstlük
- **Yalnızca sanal işlem**; aracı kurum bağlantısı veya gerçek emir gönderimi yok.
- 100.000 TL sanal başlangıç bakiyesi.
- Fiyatlar Yahoo Finance `.IS` sembollerinden alınır; ücretsiz veri gecikebilir, kesilebilir veya yanlış olabilir. Verinin son bar tarihi ayrıca gösterilir.
- Resmî Borsa İstanbul verileri için https://www.borsaistanbul.com/veriler/veri-yayini ; şirket açıklamaları için https://www.kap.org.tr/tr/
- Sıfır parasal risk yalnızca gerçek para kullanmama açısından mümkündür. Kâr garantisi yoktur.
- Sanal portföy şu sürümde Streamlit oturumunda tutulur; kalıcı veri tabanı sonraki sürüme eklenebilir.

## Yerel çalıştırma
Python 3.10+:
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Telefonda erişim
GitHub deposunu Streamlit Community Cloud'a bağlayarak dağıtım yapılabilir: https://share.streamlit.io/ . Ana dosya yolu `bist-sanal-trader/app.py` olacaktır (bu klasörün kök depo olmaması halinde uygulama ayarlarında bu yolu belirtin). Ücretsiz katman/erişim koşulları değişebilir.

## Strateji
SMA20/SMA50 kesişimi ve RSI14 tabanlı açıklayıcı sinyaller. Bu, doğrulanmış bir kârlı strateji değildir. Gerçek para ile işlem yapmaya geçiş tasarlanmamıştır.

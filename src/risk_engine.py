import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERI_DOSYASI = os.path.join(BASE_DIR, "data", "bank_ops_risk_dataset.xlsx")


class RiskEngine:
    def __init__(self, esik_deger=50, z_esik=3):
        self.esik_deger = esik_deger  # skor bu değer ve üstündeyse işlem şüpheli
        self.z_esik = z_esik  # z-score bu değerin üstündeyse tutar anormal

    def add_features(self, df, accounts, customers):
        satir_sayisi = len(df)
        df = df.merge(
            accounts[["account_id", "customer_id"]], on="account_id", how="left"
        )
        df = df.merge(
            customers[["customer_id", "segment"]], on="customer_id", how="left"
        )

        if len(df) != satir_sayisi:
            raise ValueError(
                "Join satır sayısını değiştirdi, eşleştirme kolonlarını kontrol et"
            )

        # her segment kendi ortalamasına ve standart sapmasına göre ölçülür
        grup = df.groupby("segment")["amount"]
        df["amount_z"] = (df["amount"] - grup.transform("mean")) / grup.transform("std")
        return df

    def _triggered_rules(self, row):
        # Tetiklenen her kural için (puan, neden, kural_id) üçlüsü toplar.
        # Skor, reasons ve rule_ids buradan beslenir, kurallar tek yerde durur.
        # kural_id sabit bir isimdir (neden metni z gibi sayılar içerir, kimlik olamaz).
        kurallar = []

        status = str(row.get("status", "")).upper()
        if status in ["FAILED", "ERROR"]:
            kurallar.append((30, "Başarısız işlem", "FAILED_TX"))

        channel = str(row.get("channel", "")).lower()
        if channel in ["mobile", "web"]:
            kurallar.append((15, f"Riskli kanal: {channel}", "RISKY_CHANNEL"))

        if row.get("is_international") == 1:
            kurallar.append((25, "Yurtdışı işlem", "INTERNATIONAL"))

        z = row.get("amount_z", 0)
        if pd.notna(z) and z > self.z_esik:
            kurallar.append(
                (
                    30,
                    f"Tutar kendi segmentine göre anormal (z={z:.1f})",
                    "AMOUNT_ANOMALY",
                )
            )

        return kurallar

    def calculate_score(self, row):
        skor = sum(puan for puan, neden, kural_id in self._triggered_rules(row))
        return min(skor, 100)  # skoru 100 ile sınırla

    def generate_reasons(self, row):
        return [
            f"{neden} (+{puan})" for puan, neden, kural_id in self._triggered_rules(row)
        ]

    def generate_rule_ids(self, row):
        return [kural_id for puan, neden, kural_id in self._triggered_rules(row)]

    def get_label(self, skor):
        return "suspicious" if skor >= self.esik_deger else "normal"

    def calculate(self, row):
        # tek bir işlem için tam sonuç, API'nin döneceği şey
        skor = self.calculate_score(row)
        return {
            "risk_score": skor,
            "risk_label": self.get_label(skor),
            "reasons": self.generate_reasons(row),
            "rule_ids": self.generate_rule_ids(row),  # reasons ile aynı sırada
        }

    def find_suspicious(self, df):
        df = df.copy()
        df["risk_score"] = df.apply(self.calculate_score, axis=1)
        supheli = df[df["risk_score"] >= self.esik_deger].copy()
        if supheli.empty:
            return supheli
        supheli["risk_label"] = supheli["risk_score"].apply(self.get_label)
        supheli["risk_reasons"] = supheli.apply(self.generate_reasons, axis=1).apply(
            "; ".join
        )
        return supheli

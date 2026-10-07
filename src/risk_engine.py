import pandas as pd
import numpy as np
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERI_DOSYASI = os.path.join(BASE_DIR, "data", "bank_ops_risk_dataset.xlsx")
CIKIS_DOSYASI = os.path.join(BASE_DIR, "data", "supheli_islemler.xlsx")


class RiskEngine:
    def __init__(self, esik_deger=50, z_esik=3):
        self.esik_deger = esik_deger  # skor bu değer ve üstündeyseişlem şüpheli
        self.z_esik = z_esik  # z socre bu değerin üstündeyse tutar anormal

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
                "join satır sayısını değiştrdi ,eşleştirme kollonlarını kontrol et"
            )

        # her segment kendi ortalamsını ve strandart sapmasını göre ölçülsün
        grup = df.groupby("segment")["amount"]
        df["amount_z"] = (df["amount"] - grup.transform("mean")) / grup.transform("std")
        return df

    def _triggered_rules(self, row):
        kurallar = []
        status = str(row.get("status", "")).upper()
        if status in ["FAILED", "ERROR"]:
            kurallar.append((30, "İşlem başarısız veya hata statüsünde"))

        channel = str(row.get("channel", "")).lower()
        if channel in ["mobile", "web"]:
            kurallar.append((15, "İşlem riskli kanaldan yapılmış"))

        if row.get("is_international") == 1:
            kurallar.append((25, "İşlem yurtdışı"))

        z = row.get("amount_z", 0)
        if pd.notna(z) and z > self.z_esik:
            kurallar.append((30, "Tutar anomalisi (Z-Score yüksek)"))
        return kurallar

    def calculate_score(self, row):
        skor = sum(puan for puan, neden in self._triggered_rules(row))
        return min(skor, 100)

    def generate_reasons(self, row):
        return [f"{neden} (+{puan})" for puan, neden in self._triggered_rules(row)]

    def get_label(self, skor):
        return "suspicious" if skor >= self.esik_deger else "normal"

    def calculate(self, row):
        skor = self.calculate_score(row)

        return {
            "risk_score": skor,
            "risk_label": self.get_label(skor),
            "reasons": self.generate_reasons(row),
        }

    def find_suspicious(self, df):
        df = df.copy()
        df["risk_score"] = df.apply(self.calculate_score, axis=1)
        supheli = df[df["risk_score"] >= self.esik_deger].copy()
        if supheli.empty:
            return supheli
        supheli["risk_label"] = supheli["risk_score"].apply(self.get_label)
        supheli["reasons"] = supheli.apply(self.generate_reasons, axis=1).apply(
            "; ".join
        )

        return supheli


if __name__ == "__main__":
    try:
        sheets = pd.read_excel(
            VERI_DOSYASI, sheet_name=["transactions", "accounts", "customers"]
        )

    except FileNotFoundError:
        print(
            f"{VERI_DOSYASI} dosyası bulunamadı.veri_uret.pyyi çalıştırdığından emin ol."
        )
        raise SystemExit(1)

    motor = RiskEngine()
    df = motor.add_features(
        sheets["transactions"], sheets["accounts"], sheets["customers"]
    )
    supheli_islemler = motor.find_suspicious(df)

    print(f"Toplam işlem sayısı: {len(df)}")
    print(
        f"supheli işlem sayısı (risk skoru >= {motor.esik_deger}): {len(supheli_islemler)}"
    )
    print(
        supheli_islemler[
            [
                "txn_id",
                "account_id",
                "amount",
                "status",
                "is_international",
                "risk_score",
            ]
        ].head(3)
    )

    supheli_islemler.to_excel(CIKIS_DOSYASI, index=False)

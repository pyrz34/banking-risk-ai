"""Proje1 -
Veri oluşturan kod:
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
rng = np.random.default_rng(SEED)

OUTPUT_FILE = Path("bank_ops_risk_dataset.xlsx")

N_CUSTOMERS = 600
N_ACCOUNTS_PER_CUST = (1, 3)
DAYS = 120
N_TXN = 120_000

today = pd.Timestamp(datetime.now().date())
start_date = today - pd.Timedelta(days=DAYS)


# =========================
# HELPERS
# =========================
def choice_weighted(options, probs, size):
    probs = np.array(probs, dtype=float)
    probs = probs / probs.sum()
    return rng.choice(options, size=size, replace=True, p=probs)


def random_dates(start, end, n):
    start_u = start.value // 10**9
    end_u = end.value // 10**9
    ts = rng.integers(start_u, end_u, size=n)
    return pd.to_datetime(ts, unit="s")


def clamp_int(x, lo=None, hi=None):
    x = np.asarray(x)
    if lo is not None:
        x = np.maximum(x, lo)
    if hi is not None:
        x = np.minimum(x, hi)
    return x.astype(int)


# =========================
# CUSTOMERS
# =========================
customers = pd.DataFrame(
    {
        "customer_id": np.arange(1, N_CUSTOMERS + 1),
        "segment": choice_weighted(
            ["retail", "sme", "corporate"], [0.78, 0.18, 0.04], N_CUSTOMERS
        ),
        "city": choice_weighted(
            [
                "Istanbul",
                "Ankara",
                "Izmir",
                "Bursa",
                "Antalya",
                "Adana",
                "Gaziantep",
                "Konya",
            ],
            [0.45, 0.12, 0.10, 0.08, 0.07, 0.06, 0.06, 0.06],
            N_CUSTOMERS,
        ),
        "risk_band": choice_weighted(
            ["low", "med", "high"], [0.70, 0.25, 0.05], N_CUSTOMERS
        ),
        "onboard_date": random_dates(
            start_date - pd.Timedelta(days=365 * 3), start_date, N_CUSTOMERS
        ).normalize(),
    }
)

# =========================
# ACCOUNTS
# =========================
accounts = []
acc_id = 1

for _, row in customers.iterrows():
    k = int(rng.integers(N_ACCOUNTS_PER_CUST[0], N_ACCOUNTS_PER_CUST[1] + 1))
    for _ in range(k):
        accounts.append(
            {
                "account_id": acc_id,
                "customer_id": row["customer_id"],
                "currency": rng.choice(["TRY", "USD", "EUR"], p=[0.93, 0.04, 0.03]),
                "open_date": random_dates(
                    start_date - pd.Timedelta(days=365 * 5), start_date, 1
                )[0].normalize(),
                "account_type": rng.choice(
                    ["vadesiz", "ticari", "kredi_karti", "yatirim"],
                    p=[0.72, 0.18, 0.07, 0.03],
                ),
            }
        )
        acc_id += 1

accounts = pd.DataFrame(accounts)

# =========================
# TRANSACTIONS
# =========================
account_ids = accounts["account_id"].values
picked_accounts = rng.choice(account_ids, size=N_TXN, replace=True)

txn_time = random_dates(start_date, today + pd.Timedelta(days=1), N_TXN)

channels = choice_weighted(
    ["ATM", "Mobile", "Web", "Branch"], [0.30, 0.50, 0.15, 0.05], N_TXN
)
txn_types = choice_weighted(
    ["withdraw", "transfer", "payment", "cash_deposit"], [0.25, 0.35, 0.30, 0.10], N_TXN
)

merchant_category = choice_weighted(
    [
        "grocery",
        "fuel",
        "ecommerce",
        "utility",
        "restaurant",
        "travel",
        "electronics",
        "other",
    ],
    [0.20, 0.10, 0.18, 0.12, 0.12, 0.06, 0.07, 0.15],
    N_TXN,
)

is_international = rng.choice([0, 1], size=N_TXN, p=[0.95, 0.05])
counterparty_country = np.where(
    is_international == 1,
    choice_weighted(
        ["DE", "NL", "GB", "US", "AE", "RU", "BG", "GR"],
        [0.15, 0.15, 0.20, 0.15, 0.15, 0.10, 0.05, 0.05],
        N_TXN,
    ),
    "TR",
)

acct_to_cust = accounts.set_index("account_id")["customer_id"]
cust_seg = customers.set_index("customer_id")["segment"]
cust_risk = customers.set_index("customer_id")["risk_band"]

picked_cust = acct_to_cust.loc[picked_accounts].values
seg_arr = cust_seg.loc[picked_cust].values
risk_arr = cust_risk.loc[picked_cust].values

base_mu = np.where(seg_arr == "retail", 7.8, np.where(seg_arr == "sme", 8.6, 9.6))
base_sigma = np.where(seg_arr == "retail", 0.75, np.where(seg_arr == "sme", 0.85, 0.95))
base_sigma += np.where(risk_arr == "high", 0.35, np.where(risk_arr == "med", 0.10, 0.0))

type_multiplier = np.where(
    txn_types == "withdraw",
    0.75,
    np.where(
        txn_types == "payment", 0.85, np.where(txn_types == "transfer", 1.10, 0.95)
    ),
)

intl_multiplier = np.where(is_international == 1, 1.35, 1.0)

amount = rng.lognormal(mean=base_mu, sigma=base_sigma, size=N_TXN)
amount = clamp_int(
    np.rint(amount * type_multiplier * intl_multiplier), lo=10, hi=5_000_000
)

status = rng.choice(["OK", "FAILED"], size=N_TXN, p=[0.975, 0.025])

transactions = pd.DataFrame(
    {
        "txn_id": np.arange(1, N_TXN + 1),
        "account_id": picked_accounts,
        "txn_time": txn_time,
        "channel": channels,
        "txn_type": txn_types,
        "amount": amount,
        "merchant_category": merchant_category,
        "is_international": is_international,
        "counterparty_country": counterparty_country,
        "status": status,
    }
)

# =========================
# WRITE EXCEL
# =========================
with pd.ExcelWriter(OUTPUT_FILE, engine="xlsxwriter") as writer:
    customers.to_excel(writer, sheet_name="customers", index=False)
    accounts.to_excel(writer, sheet_name="accounts", index=False)
    transactions.to_excel(writer, sheet_name="transactions", index=False)

print(f"✅ Excel dosyası oluşturuldu: {OUTPUT_FILE.resolve()}")
print("Sheet'ler: customers, accounts, transactions")

"""Held det eg har lært, på data eg ikkje har leita i?

Alt som er målt hittil er målt på heile historikken - same data som
signala vart valde ut frå. Det er den klassiske sjølvbedraget: leitar du
lenge nok i eitt datasett, finn du alltid noko som ser bra ut, og det
"noko" er som regel støy du har pussa til.

Den einaste testen som tel er denne:

    1. Del historikken i to. Rør ikkje del to.
    2. Mål alt i del ein. Vel ut det som ser best ut DER.
    3. Bruk det på del to, som aldri har vore med i utveljinga.
    4. Held kanten seg? Då er han ekte. Forsvinn han? Då var han støy.

Bruk:  .venv/bin/python backtest.py
"""

import math
import sys

from src.sources import history
from src import ensemble, technicals as T

TRAIN_FRACTION = 0.60


def _rate(closes, idxs, horizon=1):
    treff = n = 0
    for i in idxs:
        if i + horizon >= len(closes):
            continue
        n += 1
        if closes[i + horizon] > closes[i]:
            treff += 1
    return (treff / float(n) if n else None), n


def _z(rate, base, n):
    if not n or base in (0, 1):
        return 0.0
    se = math.sqrt(base * (1 - base) / n)
    return (rate - base) / se if se else 0.0


def _scan(fn, retning, lo, hi):
    ut = []
    for i in range(lo, hi):
        try:
            if fn(i) == retning:
                ut.append(i)
        except (TypeError, IndexError):
            continue
    return ut


def main():
    bars = history.fetch_daily("QQQ")
    if len(bars) < 800:
        print("For lite historikk.")
        return 1

    cross = dict((k, ensemble._aligned(bars, v))
                 for k, v in ensemble.load_cross().items())
    signals = ensemble.build_signals(bars, cross)
    closes = [b["close"] for b in bars]

    split = int(len(bars) * TRAIN_FRACTION)
    print("QQQ: %d dagar totalt" % len(bars))
    print("  LÆRER på  dag %4d-%4d  (%s til %s)"
          % (T.WARMUP, split, bars[T.WARMUP]["date"], bars[split]["date"]))
    print("  TESTAR på dag %4d-%4d  (%s til %s)  <- aldri sett før"
          % (split, len(bars) - 1, bars[split]["date"], bars[-1]["date"]))

    base_tr, n_tr = _rate(closes, range(T.WARMUP, split))
    base_te, n_te = _rate(closes, range(split, len(closes) - 1))
    print("\nBasisrate (kor ofte det stig uansett):")
    print("  lære-delen : %.1f %%  (n=%d)" % (base_tr * 100, n_tr))
    print("  test-delen : %.1f %%  (n=%d)" % (base_te * 100, n_te))

    # ---- 1. Enkeltsignal: vel i lære-delen, prøv i test-delen ----
    print("\n" + "=" * 74)
    print("1. ENKELTSIGNAL")
    print("=" * 74)
    print("%-24s %-4s %16s %18s" % ("signal", "seier", "LÆRER", "TESTAR"))
    print("-" * 74)

    valde = []
    for name, fn in signals:
        for retning in ("opp", "ned"):
            tr = _scan(fn, retning, T.WARMUP, split)
            rate_tr, cnt_tr = _rate(closes, tr)
            if cnt_tr < 40 or rate_tr is None:
                continue
            fasit_tr = base_tr if retning == "opp" else 1 - base_tr
            if retning == "ned":
                rate_tr = 1 - rate_tr
            kant_tr = rate_tr - fasit_tr
            z_tr = _z(rate_tr, fasit_tr, cnt_tr)

            te = _scan(fn, retning, split, len(closes) - 1)
            rate_te, cnt_te = _rate(closes, te)
            if cnt_te < 20 or rate_te is None:
                continue
            fasit_te = base_te if retning == "opp" else 1 - base_te
            if retning == "ned":
                rate_te = 1 - rate_te
            kant_te = rate_te - fasit_te

            merke = ""
            if kant_tr > 0 and z_tr >= 1.5:
                valde.append((name, retning, fn, kant_tr))
                merke = "  <- VALD"
            print("%-24s %-4s  %+5.1f pp (n=%3d)  %+6.1f pp (n=%3d)%s"
                  % (name, retning, kant_tr * 100, cnt_tr,
                     kant_te * 100, cnt_te, merke))

    # ---- 2. Held dei valde seg? ----
    print("\n" + "=" * 74)
    print("2. DOMEN: heldt dei som såg best ut i lære-delen?")
    print("=" * 74)
    if not valde:
        print("  Ingen signal såg eingong lovande ut i lære-delen.")
    else:
        heldt = 0
        for name, retning, fn, kant_tr in valde:
            te = _scan(fn, retning, split, len(closes) - 1)
            rate_te, cnt_te = _rate(closes, te)
            fasit_te = base_te if retning == "opp" else 1 - base_te
            if retning == "ned":
                rate_te = 1 - rate_te
            kant_te = rate_te - fasit_te
            ok = kant_te > 0
            heldt += 1 if ok else 0
            print("  %-24s %-4s  lærte %+.1f pp  ->  testa %+.1f pp   %s"
                  % (name, retning, kant_tr * 100, kant_te * 100,
                     "HELDT" if ok else "FORSVANN"))
        print("\n  %d av %d heldt seg. Ved rein flaks ville ~%.0f gjort det."
              % (heldt, len(valde), len(valde) / 2.0))

    # ---- 3. Semje: hjelper det at fleire signal peikar same veg? ----
    print("\n" + "=" * 74)
    print("3. HJELPER SEMJE? (fleire signal som peikar same veg)")
    print("=" * 74)
    print("  %-28s %8s %10s %9s" % ("", "dagar", "traff", "mot basis"))
    for krav in (2, 3, 4):
        for retning in ("opp", "ned"):
            dagar = []
            for i in range(split, len(closes) - 1):
                enige = 0
                for name, fn in signals:
                    try:
                        if fn(i) == retning:
                            enige += 1
                    except (TypeError, IndexError):
                        continue
                if enige >= krav:
                    dagar.append(i)
            rate, n = _rate(closes, dagar)
            if n < 20 or rate is None:
                print("  %-28s %8d   for få dagar" % ("%d+ signal seier %s" % (krav, retning), n))
                continue
            fasit = base_te if retning == "opp" else 1 - base_te
            if retning == "ned":
                rate = 1 - rate
            z = _z(rate, fasit, n)
            dom = "EKTE" if abs(z) >= 2 else "innanfor flaks"
            print("  %-28s %8d %9.1f %% %+8.1f pp  z=%+.1f  %s"
                  % ("%d+ signal seier %s" % (krav, retning), n,
                     rate * 100, (rate - fasit) * 100, z, dom))

    print("\n" + "=" * 74)
    print("Alle tal i TESTAR-kolonnen er på data som aldri var med då")
    print("signala vart valde ut. Det er dei einaste tala som betyr noko.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())

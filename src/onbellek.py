"""Gün 19: küçük, iş parçacığı güvenli, bellek içi LRU önbellek.

LRU = "en az yakın zamanda kullanılan atılır": dolunca, en uzun süredir dokunulmayan kayıt silinir.
Neden bellek içi: sunucu yeniden başlayınca temizlenir, yani eski prompt'la üretilmiş cevap dosyada sinsice kalmaz.
Bedeli: yeniden başlatınca ilk istekler yine pahalıdır, ve birden çok sunucu işlemi (worker) varsa her birinin kendi önbelleği olur.
Değerler kopyalanarak saklanır/döner: çağıran dönen sözlüğü değiştirirse önbellek bozulmaz.
"""
import copy
import threading
from collections import OrderedDict


class LRUOnbellek:
    def __init__(self, maks_boyut):
        if isinstance(maks_boyut, bool) or not isinstance(maks_boyut, int) or maks_boyut < 1:
            raise ValueError(f"maks_boyut 1 ya da daha büyük bir tam sayı olmalı (gelen: {maks_boyut!r})")
        self._maks = maks_boyut
        self._veri = OrderedDict()
        self._kilit = threading.Lock()
        self.isabet = 0
        self.iska = 0

    def al(self, anahtar):
        """(bulundu, değer). Bulunursa kayıt 'en yeni kullanılan' olur. Bulunamazsa (False, None)."""
        with self._kilit:
            if anahtar in self._veri:
                self._veri.move_to_end(anahtar)
                self.isabet += 1
                return True, copy.deepcopy(self._veri[anahtar])
            self.iska += 1
            return False, None

    def koy(self, anahtar, deger):
        with self._kilit:
            self._veri[anahtar] = copy.deepcopy(deger)
            self._veri.move_to_end(anahtar)
            while len(self._veri) > self._maks:
                self._veri.popitem(last=False)

    def temizle(self):
        with self._kilit:
            self._veri.clear()
            self.isabet = self.iska = 0

    def durum(self):
        with self._kilit:
            return {"boyut": len(self._veri), "maks_boyut": self._maks, "isabet": self.isabet, "iska": self.iska}

    def __len__(self):
        with self._kilit:
            return len(self._veri)

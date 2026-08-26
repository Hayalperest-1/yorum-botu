"""
Instagram, paylaşacağı görsel/videoyu internetten kendisi indirir - yani
elimizde HERKESE AÇIK bir URL olmalı. Ekstra bir barındırma servisi
kullanmak yerine, bu deponun kendisini kullanıyoruz:

  - Şablon görseller/videolar zaten `assets/story-templates/` altında
    depoda duruyor -> mevcut commit'in SHA'sını içeren
    raw.githubusercontent.com adresi üzerinden herkese açık olarak
    erişilebilirler (raw_url_for).
  - Sıradaki şablonun index'ini tutan `automation/state.json` dosyası her
    paylaşımdan sonra güncellenip commit'lenir (commit_and_push).

NOT: Bu fonksiyonlar sadece GitHub Actions runner'ı İÇİNDE, depo checkout
edilmiş haldeyken çalışacak şekilde tasarlandı.
"""

import subprocess


def _current_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def raw_url_for(repo_relative_path: str, github_repository: str) -> str:
    """Depoda ZATEN duran bir dosya için herkese açık ham (raw) URL üretir."""
    sha = _current_sha()
    return f"https://raw.githubusercontent.com/{github_repository}/{sha}/{repo_relative_path}"


def commit_and_push(paths: list, message: str) -> None:
    """Verilen dosyalardaki değişiklikleri commit'leyip push eder.

    ÖNEMLİ: push başarısız olursa (ör. aynı anda başka bir commit depoya
    gitmişse - "non-fast-forward") eskiden burası direkt hata fırlatıp
    çöküyordu; bu durumda Instagram'a paylaşım ZATEN yapılmış olsa da
    state.json'a "işlendi" olarak yazılamıyordu, bir sonraki çalıştırma
    aynı yorumu tekrar paylaşıyordu (mükerrer paylaşımların asıl sebebi
    muhtemelen buydu). Şimdi push başarısız olursa önce uzaktaki son
    değişiklikleri çekip (rebase) tekrar deniyoruz - birkaç kez."""
    subprocess.run(["git", "config", "user.name", "review-story-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "actions@users.noreply.github.com"], check=True)

    subprocess.run(["git", "add", *paths], check=True)

    result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
    # Git, "hiçbir şey stage edilmedi" durumunu duruma göre İKİ FARKLI
    # metinle bildiriyor: "nothing to commit, working tree clean" (çalışma
    # ağacında hiç değişiklik/yeni dosya yokken) VEYA "nothing added to
    # commit but untracked files present" (başka, alakasız izlenmeyen
    # dosyalar - ör. debug_screenshots/ - varken). İkisi de aslında AYNI
    # ZARARSIZ durum: verdiğimiz dosyanın içeriği zaten commit'lenmiş
    # olanla birebir aynı (ör. aynı yoruma ait görsel daha önce zaten
    # üretilip push'lanmış) - eskiden sadece ilk metni tanıyorduk, ikinci
    # metin geldiğinde gereksiz yere hata fırlatıp o yorumu sonsuza kadar
    # başarısız gösteriyorduk.
    nothing_staged_markers = ("nothing to commit", "nothing added to commit")
    if result.returncode != 0 and not any(m in result.stdout for m in nothing_staged_markers):
        raise RuntimeError(f"git commit başarısız: {result.stdout}\n{result.stderr}")

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        push = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push.returncode == 0:
            return
        print(f"[git_publish] push başarısız (deneme {attempt}/{max_attempts}), "
              f"uzaktaki değişiklikler çekilip tekrar denenecek: {push.stderr.strip()}")
        subprocess.run(["git", "fetch", "origin", "main"], check=True)
        rebase = subprocess.run(
            ["git", "rebase", "origin/main"], capture_output=True, text=True
        )
        if rebase.returncode != 0:
            # Rebase çakışması - kurtarmaya çalışmak riskli, pes ediyoruz.
            subprocess.run(["git", "rebase", "--abort"], capture_output=True, text=True)
            raise RuntimeError(
                f"git push {max_attempts} denemede de başarısız oldu ve rebase çakıştı:\n"
                f"{push.stderr}\n{rebase.stdout}\n{rebase.stderr}"
            )

    raise RuntimeError(f"git push {max_attempts} denemede de başarısız oldu, son hata: {push.stderr}")

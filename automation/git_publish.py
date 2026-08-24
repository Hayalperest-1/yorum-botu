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
    """Verilen dosyalardaki değişiklikleri commit'leyip push eder."""
    subprocess.run(["git", "config", "user.name", "review-story-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "actions@users.noreply.github.com"], check=True)

    subprocess.run(["git", "add", *paths], check=True)

    result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
    if result.returncode != 0 and "nothing to commit" not in result.stdout:
        raise RuntimeError(f"git commit başarısız: {result.stdout}\n{result.stderr}")

    subprocess.run(["git", "push"], check=True)

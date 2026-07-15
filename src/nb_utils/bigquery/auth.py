import subprocess

def relogin_adc():
    print("🔐 Требуется повторная авторизация Google Cloud...")
    subprocess.run(
        ["gcloud", "auth", "application-default", "login"],
        check=True,
    )
    print("✅ Авторизация завершена")

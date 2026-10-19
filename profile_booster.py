import asyncio
import time
from typing import Dict, Any
from playwright.async_api import async_playwright
from config import ConfigManager

class ProfileBooster:
    """Boosts Naukri profile ranking by updating the Profile Headline."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    async def boost_profile(self) -> bool:
        user_data_dir = self.config.get("user_data_dir")
        headless = self.config.get("headless", False)
        target_headline = self.config.get("headline", "").strip()

        print("[Profile Booster] Launching browser to refresh Naukri profile...")

        if user_data_dir and os.path.exists(user_data_dir):
            for lock_f in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
                lp = os.path.join(user_data_dir, lock_f)
                if os.path.exists(lp):
                    try:
                        os.remove(lp)
                    except Exception:
                        pass

        async with async_playwright() as p:
            launch_args = ["--disable-blink-features=AutomationControlled", "--start-maximized"]
            context = None
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel="chrome",
                    headless=headless,
                    args=launch_args,
                    no_viewport=True
                )
            except Exception:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=headless,
                    args=launch_args,
                    no_viewport=True
                )

            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page = await context.new_page()
            await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)

            # Check if user is logged in
            if "naukri.com/nlogin/login" in page.url or "login" in page.url.lower():
                print("[Profile Booster] User is not logged in. Please log in first.")
                await context.close()
                return False

            print("[Profile Booster] Navigated to profile page.")

            # Locate edit headline button/icon
            try:
                # Click edit headline pencil icon
                edit_icon = page.locator("span.edit.icon:has-text('edit')").first
                if not await edit_icon.is_visible():
                    edit_icon = page.locator("div.widgetHead span.edit").first

                if await edit_icon.is_visible():
                    await edit_icon.click()
                    await asyncio.sleep(2)
                else:
                    # Alternative selector
                    await page.click("text='Resume headline'", timeout=5000)
                    await asyncio.sleep(2)

                # Find input area for resume headline
                headline_area = page.locator("textarea#resumeHeadlineTxt, textarea.resumeHeadlineTxt, textarea").first
                if await headline_area.is_visible():
                    current_text = await headline_area.input_value()
                    print(f"[Profile Booster] Current Headline: {current_text}")

                    # Decide new text (toggle ending dot/space to register as an update)
                    if target_headline:
                        new_headline = target_headline
                        if new_headline == current_text:
                            new_headline += " ." if not current_text.endswith(" .") else ""
                            if new_headline.endswith(" ."):
                                new_headline = new_headline[:-2]
                    else:
                        new_headline = current_text + " " if not current_text.endswith(" ") else current_text.strip()

                    await headline_area.fill(new_headline)
                    await asyncio.sleep(1)

                    # Click Save
                    save_btn = page.locator("button.btn-primary:has-text('Save'), button:has-text('Save')").first
                    await save_btn.click()
                    await asyncio.sleep(3)

                    print("[Profile Booster] Profile headline successfully updated & saved! Naukri ranking refreshed.")
                    await context.close()
                    return True
                else:
                    print("[Profile Booster] Could not locate resume headline input field.")

            except Exception as e:
                print(f"[Profile Booster] Error while updating headline: {e}")

            await context.close()
            return False

def run_booster():
    cfg = ConfigManager.load_config()
    booster = ProfileBooster(cfg)
    return asyncio.run(booster.boost_profile())

if __name__ == "__main__":
    run_booster()

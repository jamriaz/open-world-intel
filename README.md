# Open World Intel - GTA channel (Roman Urdu)

Roz 2 long + 3 Shorts, GitHub cloud par, stock footage + AI voice. Videos **private** upload hoti hain, tum Studio se publish karo.
Pehle channel (Curious Orbit) se ye bilkul alag hai: naya channel, naya Google Cloud project, naya repo.

## Step 1: Naya YouTube channel
Naam "Open World Intel". Phone verify karo (youtube.com/verify) taake custom thumbnail chale. Branding folder se logo/banner/description lagao.

## Step 2: Naya Google Cloud project (alag, taake quota alag ho)
1. console.cloud.google.com > New project "owi-uploader" > Library > **YouTube Data API v3** > Enable.
2. Branding/Audience: External, app name, support email, homepage + privacy policy URL (purana Google Doc wala link dobara use kar sakte ho) > **Publish app**.
3. Credentials > Create OAuth client ID > **Desktop app** > JSON download > naam `client_secret.json`.

## Step 3: Is folder mein files rakho
`client_secret.json`, `gemini_key.txt`, `pixabay_key.txt` (purani keys copy kar sakte ho).

## Step 4: Token
`python get_token.py client_secret.json` - browser mein account chooser mein **Open World Intel wala channel** chuno. `token.json` banegi.

## Step 5: Cloud
`python setup_cloud.py` (repo **public** banta hai taake GitHub minutes khatam na hon; keys/token secrets mein jaate hain, code mein nahi).

## Step 6: Test
- `gh workflow run shorts.yml -f mode=short -f dry_run=1` phir `gh run watch`
- phir long: `-f mode=long -f dry_run=1`
- theek ho to `dry_run=0` se asli upload, ya schedule ka intezar.

## Dhyan rakho
- Ye stock footage hai, game footage nahi: views screenshot wale channels jitne nahi aayenge.
- Facts Google Search se check hote hain, phir bhi publish se pehle GTA 6 wali baatein ek nazar dekh lo.
- Pehle ~10 video khud dekh kar publish karo. Koi guarantee nahi.

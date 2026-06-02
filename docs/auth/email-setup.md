# Auth confirmation emails (Resend + Supabase SMTP)

Signup uses email confirmation with a 6-digit code typed in-app (`verifyOtp`). The
code is delivered by Supabase auth email, sent through Resend via Custom SMTP.
The email body is the template in
[`supabase/email-templates/confirm-signup.html`](../../supabase/email-templates/confirm-signup.html).

Without Custom SMTP, Supabase's built-in sender has low rate limits and a generic
template. Fine for local dev, not for real users.

## One-time setup

### 1. Resend

1. Create a Resend account.
2. Add your sending domain and complete DNS verification (SPF, DKIM records).
3. Create an API key.

### 2. Supabase Custom SMTP

Project Settings → Authentication → SMTP Settings → enable Custom SMTP:

- Host: `smtp.resend.com`
- Port: `465` (SSL) or `587`
- Username: `resend`
- Password: your Resend API key
- Sender email: an address on your verified domain, e.g. `no-reply@yourdomain.com`
- Sender name: `Suhuf`

### 3. Email template

Authentication → Email Templates → "Confirm signup":

- Subject: e.g. `Your Suhuf code`
- Message body: paste the full contents of
  `supabase/email-templates/confirm-signup.html`.
- Keep `{{ .Token }}` in the body. Do not switch the body to a confirmation link,
  the app expects a typed code.

### 4. Token validity (optional)

Authentication → email OTP expiry defaults to 1 hour (3600s). The template text
says "expires in 1 hour", so update the copy if you change this.

## Verify

Sign up at `/login` with a real address. Confirm the email arrives from your
sender, the code renders cleanly, and entering it logs you in.

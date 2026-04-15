import { Resend } from "resend";

function getResend() {
  return new Resend(process.env.RESEND_API_KEY);
}

export async function sendWelcomeEmail({
  email,
  position,
  referralCode,
}: {
  email: string;
  position: number;
  referralCode: string;
}) {
  const referralLink = `${process.env.NEXT_PUBLIC_URL || "https://suhuf.ai"}/r/${referralCode}`;

  const resend = getResend();
  const FROM = process.env.EMAIL_FROM || "suhuf <onboarding@resend.dev>";

  await resend.emails.send({
    from: FROM,
    to: email,
    subject: `You're #${position} on the Suhuf waitlist`,
    html: `
      <div style="font-family: Georgia, serif; max-width: 520px; margin: 0 auto; padding: 40px 20px;">
        <p style="font-style: italic; font-size: 22px; color: #2A1F17; margin-bottom: 32px;">suhuf</p>

        <h1 style="font-size: 28px; color: #2A1F17; font-weight: normal; margin-bottom: 16px;">
          You're #${position} on the waitlist
        </h1>

        <p style="font-size: 16px; color: #2A1F1780; line-height: 1.6; margin-bottom: 24px;">
          Thanks for joining. We're building something special for students of classical Arabic, and you'll be among the first to try it.
        </p>

        <div style="background: #F5EEE4; border-radius: 12px; padding: 24px; margin-bottom: 24px;">
          <p style="font-size: 14px; color: #2A1F17; font-weight: 600; margin-bottom: 8px;">
            Move up the list
          </p>
          <p style="font-size: 14px; color: #2A1F1780; line-height: 1.5; margin-bottom: 16px;">
            Share your referral link. Each signup moves you closer to the front.
          </p>
          <a href="${referralLink}" style="display: inline-block; background: #2A1F17; color: white; padding: 12px 24px; border-radius: 100px; text-decoration: none; font-size: 14px;">
            ${referralLink}
          </a>
        </div>

        <p style="font-size: 13px; color: #2A1F1740;">
          &mdash; The Suhuf team
        </p>
      </div>
    `,
  });
}

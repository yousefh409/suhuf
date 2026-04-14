const CHARSET = "abcdefghjkmnpqrstuvwxyz23456789"; // no confusing chars

export function generateReferralCode(): string {
  let code = "";
  for (let i = 0; i < 8; i++) {
    code += CHARSET[Math.floor(Math.random() * CHARSET.length)];
  }
  return `shf_${code}`;
}

export function isValidReferralCode(code: string): boolean {
  return /^shf_[a-z2-9]{8}$/.test(code);
}

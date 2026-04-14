const crypto = require('crypto');

const CryptoDigestAlgorithm = {
  SHA1: 'SHA-1',
  SHA256: 'SHA-256',
  SHA384: 'SHA-384',
  SHA512: 'SHA-512',
  MD2: 'MD2',
  MD4: 'MD4',
  MD5: 'MD5',
};

const CryptoEncoding = {
  HEX: 'hex',
  BASE64: 'base64',
};

function algorithmToNodeName(algorithm) {
  switch (algorithm) {
    case 'SHA-1': return 'sha1';
    case 'SHA-256': return 'sha256';
    case 'SHA-384': return 'sha384';
    case 'SHA-512': return 'sha512';
    case 'MD5': return 'md5';
    default: return algorithm.toLowerCase().replace('-', '');
  }
}

async function digestStringAsync(algorithm, data, options = {}) {
  const encoding = options.encoding ?? 'hex';
  const nodeAlgorithm = algorithmToNodeName(algorithm);
  const hash = crypto.createHash(nodeAlgorithm).update(data, 'utf8').digest(encoding === 'hex' ? 'hex' : 'base64');
  return hash;
}

module.exports = {
  CryptoDigestAlgorithm,
  CryptoEncoding,
  digestStringAsync,
};

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { sentence } = await req.json();

    if (!sentence) {
      return new Response(
        JSON.stringify({ error: 'sentence is required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const systemPrompt = `You are an expert translator of classical Arabic texts. Translate the given Arabic sentence to English, preserving the scholarly register.

Also identify the primary root (جذر) of the most significant content word in the sentence and provide 4-6 related words from the same root.

For Islamic/Arabic terms that are commonly transliterated (e.g., hadith, fiqh, sunnah, i'rab), transliterate them and add a brief parenthetical gloss on first use.

Return a JSON object with:
- translation: the English translation
- related_words: array of objects with { word (Arabic with tashkeel), root (Arabic letters spaced), meaning (English) }

Return ONLY valid JSON, no markdown fences.`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 600,
        messages: [
          { role: 'user', content: `Translate this Arabic sentence and provide related vocabulary:\n\n${sentence}` },
        ],
        system: systemPrompt,
      }),
    });

    const data = await response.json();
    const text = data.content[0].text;
    const result = JSON.parse(text);

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});

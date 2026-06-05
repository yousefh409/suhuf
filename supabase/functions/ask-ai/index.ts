import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const OPENROUTER_API_KEY = Deno.env.get('OPENROUTER_API_KEY')!;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { word, sentence, question, history } = await req.json();

    if (!word || !sentence || !question) {
      return new Response(
        JSON.stringify({ error: 'word, sentence, and question are required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const systemPrompt = `You are a patient, knowledgeable Arabic grammar teacher. A student is reading a classical Arabic text and has a question about a specific word.

Context:
- Word: ${word}
- Sentence: ${sentence}

Answer their question clearly, mixing Arabic grammar terminology with English explanations. Use examples when helpful. Keep answers concise (2-4 paragraphs max). When referencing Arabic grammatical terms, show them in Arabic script.`;

    const messages = [
      ...(history || []).map((m: { role: string; content: string }) => ({
        role: m.role,
        content: m.content,
      })),
      { role: 'user', content: question },
    ];

    const response = await fetch('https://openrouter.ai/api/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'anthropic/claude-sonnet-4',
        max_tokens: 800,
        messages,
        system: systemPrompt,
      }),
    });

    const data = await response.json();
    const text = data.content[0].text;

    return new Response(JSON.stringify({ response: text }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});

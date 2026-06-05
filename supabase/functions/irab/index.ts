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
    const { word, sentence, position } = await req.json();

    if (!word || !sentence) {
      return new Response(
        JSON.stringify({ error: 'word and sentence are required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const systemPrompt = `You are an expert Arabic grammarian (نحوي). You analyze Arabic words in their sentence context and return grammatical analysis (إعراب).

Return a JSON object with these exact fields:
- pos: part of speech in English (noun, verb, particle, adjective, pronoun, etc.)
- role: grammatical role in English (subject, object, predicate, mudaf_ilayh, khabar, mubtada, etc.)
- role_ar: grammatical role in Arabic (مبتدأ، خبر، فاعل، مفعول به، مضاف إليه، etc.)
- case: grammatical case in English (marfu, mansub, majrur, majzum, mabni)
- case_ar: grammatical case in Arabic (مرفوع، منصوب، مجرور، مجزوم، مبني)
- marker: case marker in English (damma, fatha, kasra, sukun, tanween_damma, tanween_fatha, tanween_kasra)
- marker_ar: case marker in Arabic (ضمة، فتحة، كسرة، سكون، تنوين ضم، تنوين فتح، تنوين كسر)
- why: 1-2 sentence explanation mixing Arabic grammar terms with English explanation of WHY this word has this case in this sentence. Reference the specific grammar rule.
- meaning: brief English dictionary meaning of the word

Return ONLY valid JSON, no markdown fences.`;

    const userPrompt = `Analyze this word in context:

Word: ${word}
Full sentence: ${sentence}
Position in sentence: ${position}

Provide the full إعراب analysis as JSON.`;

    const response = await fetch('https://openrouter.ai/api/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'anthropic/claude-sonnet-4',
        max_tokens: 500,
        messages: [
          { role: 'user', content: userPrompt },
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

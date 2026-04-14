const testimonials = [
  {
    quote:
      "Students always ask me how to start reading Arabic texts on their own. Something like Suhuf that meets them where they are and helps with the grammar in real time is exactly what I'd point them to. It fills a gap that's been open for a long time.",
    name: "Imam Fuad Mohamed",
    role: "Religious Director, MCA",
    image: "/testimonials/fuad.jpg",
  },
  {
    quote:
      "When you're going through seminary, you're assigned dozens of texts and expected to read them with full comprehension. Suhuf makes that realistic. Being able to tap any word and see its role in the sentence, its root, its meaning, that changes the whole experience.",
    name: "Zaid Yousef",
    role: "Masters Student, The Islamic Seminary of America",
    image: "/testimonials/zaid.jpg",
  },
  {
    quote:
      "For centuries, students needed years with a sheikh just to be able to read these books independently. Suhuf doesn't replace that, but it makes the journey faster. It gives students the confidence to open a book and actually engage with the Arabic on their own.",
    name: "Sheikh Mohammed Salman",
    role: "Al-Azhar University",
    image: "/testimonials/mohammed.jpg",
  },
  {
    quote:
      "Every Arabic student I know has the same problem. You want to read a real book but you're constantly switching between five tabs just to understand one sentence. Suhuf puts everything in one place. Someone finally built the thing we all needed.",
    name: "Osman Saeday",
    role: "Founder, Bayaan",
    image: "/testimonials/osman.jpg",
  },
  {
    quote:
      "As someone building in tech, I know how rare it is for a product to actually understand its users. Suhuf isn't just another reading app. It solves a real problem that Arabic students deal with every day, and it does it in a way that feels natural.",
    name: "Ibrahim Izzeldin",
    role: "Founder, Flick",
    image: "/testimonials/ibrahim.jpg",
  },
];

function Card({
  quote,
  name,
  role,
  image,
}: {
  quote: string;
  name: string;
  role: string;
  image: string;
}) {
  return (
    <div className="flex flex-col justify-between flex-shrink-0 w-[320px] sm:w-[600px] rounded-2xl px-5 sm:px-7 py-5 gap-4 bg-white">
      <p className="text-sm text-ink/60 leading-[1.5]">{quote}</p>
      <div className="flex items-center gap-3">
        <img
          src={image}
          alt={name}
          className="w-10 h-10 rounded-full object-cover bg-ink/10"
        />
        <div>
          <p className="text-sm font-medium text-ink">{name}</p>
          <p className="text-xs text-ink/40 mt-0.5">{role}</p>
        </div>
      </div>
    </div>
  );
}

export default function SocialProof() {
  const doubled = [...testimonials, ...testimonials];

  return (
    <section className="w-full pt-12 pb-24 overflow-hidden">
      <div className="flex gap-5 px-10 animate-marquee w-max">
        {doubled.map((t, i) => (
          <Card key={i} {...t} />
        ))}
      </div>
    </section>
  );
}

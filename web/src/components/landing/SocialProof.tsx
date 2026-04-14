const testimonials = [
  {
    quote:
      "This is exactly what I needed during my Madinah University entrance prep. The i\u2019rab corrections alone saved me months.",
    name: "Bilal Mahmoud",
    role: "Student, Madinah University",
  },
  {
    quote:
      "I\u2019ve been teaching nahw for 15 years. This is the first tool I\u2019d actually recommend to my students \u2014 it corrects the way I correct.",
    name: "Sheikh Ahmad al-Rashidi",
    role: "Instructor, Umm al-Qura University",
  },
  {
    quote:
      "Finally, something that teaches i\u2019rab the way a sheikh would \u2014 by correcting you as you read, not through dry grammar drills.",
    name: "Ustadh Khalid Hasan",
    role: "Islamic studies teacher, London",
  },
  {
    quote:
      "I used to dread reading aloud in class. After two weeks with suhuf, my teacher noticed the difference before I did.",
    name: "Yusra Mansoor",
    role: "2nd year, Islamic Univ. of Madinah",
  },
  {
    quote:
      "My students\u2019 confidence reading classical texts has improved dramatically. Suhuf fills a gap no textbook can.",
    name: "Sheikh Omar Farouq",
    role: "Qur\u2019anic Arabic instructor, Al-Azhar",
  },
];

function Card({
  quote,
  name,
  role,
}: {
  quote: string;
  name: string;
  role: string;
}) {
  return (
    <div className="flex flex-col flex-shrink-0 w-[320px] rounded-2xl p-7 gap-4 bg-white">
      <p className="text-sm text-ink/60 leading-[1.6] flex-1">{quote}</p>
      <div>
        <p className="text-sm font-medium text-ink">{name}</p>
        <p className="text-xs text-ink/40 mt-0.5">{role}</p>
      </div>
    </div>
  );
}

export default function SocialProof() {
  const doubled = [...testimonials, ...testimonials];

  return (
    <section className="w-full py-12 overflow-hidden">
      <div className="flex gap-5 px-10 animate-marquee w-max">
        {doubled.map((t, i) => (
          <Card key={i} {...t} />
        ))}
      </div>
    </section>
  );
}

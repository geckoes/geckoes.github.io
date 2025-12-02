

export default function Skills() {
const skills = ['PHP', 'HTML', 'CSS', 'Java', 'C', 'Docker', 'React', 'Vue', 'Go'];


return (
<section id="skills" className="py-32 px-6 bg-[#17171E] text-white">
<h2 className="text-4xl font-bold mb-8 text-[#5929B3] text-center">Skills</h2>
<div className="flex flex-wrap justify-center gap-4">
{skills.map((skill, idx) => (
<span key={idx} className="px-4 py-2 bg-[#3A1E73] rounded-lg font-semibold">{skill}</span>
))}
</div>
</section>
);
}

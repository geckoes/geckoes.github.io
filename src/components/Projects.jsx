
export default function Projects() {
const projectList = [
{ name: 'SkillForge', link: 'https://github.com/geckoes/skillforge' },
{ name: 'Impossible Mission', link: '#' },
{ name: 'MindMesh', link: '#' }
];


return (
<section id="projects" className="py-32 px-6 bg-[#0F0F14] text-white">
<h2 className="text-4xl font-bold mb-12 text-[#5929B3] text-center">Projects</h2>
<div className="grid md:grid-cols-3 gap-8">
{projectList.map((proj, idx) => (
<a key={idx} href={proj.link} target="_blank" className="card">
<h3 className="text-xl font-semibold mb-2">{proj.name}</h3>
<p className="opacity-70">Click to view project on GitHub or demo.</p>
</a>
))}
</div>
</section>
);
}

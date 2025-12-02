

export default function Navbar() {
const links = [
{ name: 'Home', href: '#hero' },
{ name: 'About', href: '#about' },
{ name: 'Projects', href: '#projects' },
{ name: 'Skills', href: '#skills' },
{ name: 'Contact', href: '#contact' },
];


return (
<nav className="fixed top-0 left-0 w-full bg-[#0F0F14] bg-opacity-90 backdrop-blur-md shadow-md z-50">
<div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
<div className="text-2xl font-bold text-[#5929B3]">Filippo</div>
<div className="flex space-x-6">
{links.map((link, idx) => (
<a key={idx} href={link.href} className="text-white font-medium hover:text-[#7C4DFF] transition">
{link.name}
</a>
))}
</div>
</div>
</nav>
);
}

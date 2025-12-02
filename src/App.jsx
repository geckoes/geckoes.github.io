import About from './components/About';
import Contact from './components/Contact';
import Footer from './components/Footer';
import Hero from './components/Hero';
import Nav from './components/Navbar';
import Projects from './components/Projects';
import Skills from './components/Skills';


export default function App() {
return (
<div className="App bg-[#0F0F14] text-white">
<Nav />
<Hero />
<About />
<Projects />
<Skills />
<Contact />
<Footer />
</div>
);
}

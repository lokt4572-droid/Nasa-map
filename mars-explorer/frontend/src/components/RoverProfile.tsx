import { useEffect, useState } from "react";
import "../styles/rover.css";

type RoverProfileProps = {
    onNext: () => void;
};

type Specifications = {
    name: string;
    mass: string;
    speed: string;
    wheels: string;
    description: string;
};

const emptySpecs: Specifications = {
    name: "",
    mass: "",
    speed: "",
    wheels: "",
    description: "",
};

export default function RoverProfile({ onNext }: RoverProfileProps) {
    const [specs, setSpecs] = useState<Specifications>(emptySpecs);
    const [savedSpecs, setSavedSpecs] = useState<Specifications | null>(null);
    const [isEditing, setIsEditing] = useState(false);

    // Load saved data when the page opens
    useEffect(() => {
        const saved = localStorage.getItem("roverSpecifications");

        if (saved) {
            const data = JSON.parse(saved);
            setSpecs(data);
            setSavedSpecs(data);
        }
    }, []);

    // Update input values
    function handleChange(
        e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
    ) {
        const { name, value } = e.target;

        setSpecs((prev) => ({
            ...prev,
            [name]: value,
        }));
    }

    // Save specifications
    function handleSave() {
        localStorage.setItem("roverSpecifications", JSON.stringify(specs));
        setSavedSpecs(specs);
        setIsEditing(false);
    }

    return (
        <div className="rover-page">
            <nav className="rover-nav">
                <a href="#" className="rover-logo">
                    MARS<span>.</span>EXPLORER
                </a>

                <span className="rover-page-number">02 / 03</span>

                <span className="rover-status">
                    <span className="rover-status-dot" />
                    ROVER ONLINE
                </span>
            </nav>

            <main className="rover-content">
                <div className="rover-heading">
                    <p className="rover-eyebrow">NASA / MARS SCIENCE LABORATORY</p>

                    <h1>
                        MEET
                        <br />
                        <span>CURIOSITY.</span>
                    </h1>

                    <p className="rover-description">
                        An autonomous robotic explorer designed to investigate
                        the geology and climate of Mars.
                    </p>
                </div>

                <div className="rover-image">
                    <img
                        src="/images1/curiosity-rover.jpg"
                        alt="NASA Curiosity rover on Mars"
                    />
                    <span>NASA / JPL-CALTECH</span>
                </div>

                {(!savedSpecs || isEditing) && (
                    <section className="rover-specifications">
                        <p className="rover-eyebrow">ROVER CONFIGURATION</p>
                        <h2>ENTER SPECIFICATIONS</h2>

                        <div className="rover-form">
                            <label>
                                Rover Name
                                <input
                                    name="name"
                                    value={specs.name}
                                    onChange={handleChange}
                                    placeholder="Enter rover name"
                                />
                            </label>

                            <label>
                                Mass (kg)
                                <input
                                    type="number"
                                    name="mass"
                                    value={specs.mass}
                                    onChange={handleChange}
                                    placeholder="Enter mass"
                                />
                            </label>

                            <label>
                                Speed (cm/s)
                                <input
                                    type="number"
                                    name="speed"
                                    value={specs.speed}
                                    onChange={handleChange}
                                    placeholder="Enter speed"
                                />
                            </label>

                            <label>
                                Number of Wheels
                                <input
                                    type="number"
                                    name="wheels"
                                    value={specs.wheels}
                                    onChange={handleChange}
                                    placeholder="Enter number of wheels"
                                />
                            </label>

                            <label className="rover-description-field">
                                Mission Description
                                <textarea
                                    name="description"
                                    value={specs.description}
                                    onChange={handleChange}
                                    placeholder="Describe the rover mission..."
                                />
                            </label>

                            <button
                                type="button"
                                className="rover-next-button"
                                onClick={handleSave}
                            >
                                SAVE SPECIFICATIONS
                                <span>↗</span>
                            </button>
                        </div>
                    </section>
                )}

                {savedSpecs && (
                    <section className="rover-saved">
                        <p className="rover-eyebrow">SAVED DATA</p>
                        <h2>{savedSpecs.name || "ROVER SPECIFICATIONS"}</h2>
                        <button
                            type="button"
                            className="rover-edit-button"
                            onClick={() => setIsEditing(true)}
                        >
                            EDIT SPECIFICATIONS
                        </button>

                        <div className="rover-info">
                            <div>
                                <span className="rover-info-label">MASS</span>
                                <strong>{savedSpecs.mass || "—"} kg</strong>
                            </div>

                            <div>
                                <span className="rover-info-label">SPEED</span>
                                <strong>{savedSpecs.speed || "—"} cm/s</strong>
                            </div>

                            <div>
                                <span className="rover-info-label">WHEELS</span>
                                <strong>{savedSpecs.wheels || "—"}</strong>
                            </div>
                        </div>

                        <p>{savedSpecs.description}</p>
                    </section>
                )}

                <section className="rover-systems">
                    <p className="rover-eyebrow">ENGINEERING / TECHNOLOGY</p>
                    <h2>ROVER SYSTEMS</h2>

                    <div className="rover-systems-grid">
                        <div className="rover-system-card">
                            <span>01 / MOBILITY</span>
                            <h3>WHEEL SYSTEM</h3>
                            <p>
                                Six independently driven wheels help Curiosity
                                travel across the rocky Martian surface.
                            </p>
                        </div>

                        <div className="rover-system-card">
                            <span>02 / IMAGING</span>
                            <h3>CAMERA SYSTEM</h3>
                            <p>
                                Cameras capture images of the Martian landscape
                                and help scientists study the terrain.
                            </p>
                        </div>

                        <div className="rover-system-card">
                            <span>03 / SCIENCE</span>
                            <h3>ROBOTIC ARM</h3>
                            <p>
                                Scientific instruments on the robotic arm
                                examine rocks and soil.
                            </p>
                        </div>

                        <div className="rover-system-card">
                            <span>04 / ENERGY</span>
                            <h3>POWER SYSTEM</h3>
                            <p>
                                A radioisotope power system supplies electricity
                                and heat to the rover.
                            </p>
                        </div>
                    </div>

                    <button className="rover-next-button" onClick={onNext}>
                        NEXT: PLAN ROUTE
                        <span>↗</span>
                    </button>
                </section>
            </main>
        </div>
    );
}
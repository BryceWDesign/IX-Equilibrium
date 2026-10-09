system SharedControl {
    tick 10 ms;
    input operator : bool fresh 30 ms;
    sensor requested : mps fresh 30 ms uncertainty 0 mps;
    sensor distance : m fresh 30 ms uncertainty 0.01 m;
    actuator left : mps range [-0.1 mps, 0.1 mps] safe 0 mps slew 2 mps2;
    actuator right : mps range [-0.1 mps, 0.1 mps] safe 0 mps slew 2 mps2;
    capability command left;
    capability command right;
    state waiting initial { when operator -> motion; }
    state motion {
        require distance > 0.3 m;
        command left = clamp(requested, -0.1 mps, 0.1 mps);
        command right = clamp(requested, -0.1 mps, 0.1 mps);
        when not operator -> waiting;
    }
    state stopped terminal { }
    on fault -> stopped;
}

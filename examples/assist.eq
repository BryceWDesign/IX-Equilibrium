// Research supervisory language; the host owns grants and independent stops.
system AdaptiveAssist {
    tick 20 ms;
    sensor vision : m fresh 100 ms uncertainty 0.01 m;
    sensor proximity : m fresh 100 ms uncertainty 0.01 m;
    sensor tactile : m fresh 100 ms uncertainty 0.01 m;
    sensor load : N fresh 60 ms uncertainty 0.1 N;
    input intent : bool fresh 100 ms;
    mesh clearance : m = quorum(vision, proximity, tactile) tolerance 0.08 m require 2;
    param gain : scalar = 0.5 within [0.1, 1.0] rate 0.1;
    actuator arm : mps range [-0.2 mps, 0.2 mps] safe 0 mps slew 1 mps2;
    capability command arm;
    invariant contact_load : load < 5 N;
    state idle initial {
        when intent -> moving;
    }
    state moving {
        require clearance > 0.2 m;
        adapt gain = clamp(clearance / 1 m, 0.1, 1.0);
        command arm = gain * 0.2 mps;
        when not intent -> idle;
        after 2 s -> complete;
    }
    state complete terminal { }
    state stopped terminal { }
    on fault -> stopped;
}

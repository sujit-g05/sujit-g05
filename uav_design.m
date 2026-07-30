% =========================================================================
% Advanced Fixed-Wing UAV Design, Analysis, and Control Script
% Design Requirements:
% MTOW = 5 kg
% Payload = 0.25 kg (250 grams)
%
% This script performs:
% 1. Aircraft Parameters Initialization
% 2. Aerodynamics Analysis
% 3. Performance Analysis
% 4. Stability Analysis (Longitudinal)
% 5. Control Design (LQR Pitch Controller)
% =========================================================================

clear; clc; close all;

%% 1. Aircraft Parameters Initialization (Base parameters for 5kg UAV)
disp('--- 1. Aircraft Parameters ---');

% Weights
W_MTOW = 5.0;            % Maximum Takeoff Weight [kg]
W_payload = 0.25;        % Payload Weight [kg]
W_empty = 3.0;           % Empty Weight [kg] (Structure, Avionics, Propulsion)
W_battery = W_MTOW - W_payload - W_empty; % Battery Weight [kg]
g = 9.81;                % Gravity acceleration [m/s^2]
Weight_N = W_MTOW * g;   % Weight in Newtons [N]

fprintf('MTOW: %.2f kg\n', W_MTOW);
fprintf('Payload: %.2f kg\n', W_payload);
fprintf('Battery Weight: %.2f kg\n', W_battery);

% Geometry & Wing Design (Based on typical RC/UAV sizing, Raymer approach)
W_S = 10;                % Wing Loading [kg/m^2]
S = W_MTOW / W_S;        % Wing Area [m^2]
AR = 8;                  % Aspect Ratio
b = sqrt(AR * S);        % Wingspan [m]
c_mac = S / b;           % Mean Aerodynamic Chord [m]

fprintf('Wing Area (S): %.2f m^2\n', S);
fprintf('Wingspan (b): %.2f m\n', b);
fprintf('Mean Aerodynamic Chord (MAC): %.2f m\n', c_mac);

% Environment (Sea level)
rho = 1.225;             % Air density [kg/m^3]

%% 2. Aerodynamics Analysis
disp('--- 2. Aerodynamics Analysis ---');

% Airfoil and Drag parameters (e.g., Clark Y)
CL_max = 1.3;            % Maximum Lift Coefficient
CD0 = 0.025;             % Zero-lift drag coefficient
e = 0.85;                % Oswald efficiency factor
K = 1 / (pi * e * AR);   % Induced drag factor

% Drag Polar
alpha = -5:1:15;         % Angle of attack [deg]
CL_alpha = 0.1 * (180/pi); % Lift curve slope [1/rad] roughly 2*pi / (1 + 2/AR)
CL = CL_alpha * (alpha * pi/180) + 0.3; % Lift coefficient vs alpha (assumed alpha_0 = -3 deg)
CL = min(CL, CL_max);    % Cap at stall
CD = CD0 + K * CL.^2;    % Drag coefficient

figure('Name', 'Aerodynamics Analysis');
subplot(1,2,1);
plot(alpha, CL, 'b', 'LineWidth', 2);
xlabel('\alpha [deg]'); ylabel('C_L');
title('Lift Curve'); grid on;

subplot(1,2,2);
plot(CD, CL, 'r', 'LineWidth', 2);
xlabel('C_D'); ylabel('C_L');
title('Drag Polar'); grid on;

% L/D max
L_D = CL ./ CD;
[LD_max, idx_LD] = max(L_D);
fprintf('Max L/D: %.2f at CL = %.2f\n', LD_max, CL(idx_LD));

%% 3. Performance Analysis
disp('--- 3. Performance Analysis ---');

% Stall Speed
V_stall = sqrt(2 * Weight_N / (rho * S * CL_max));
fprintf('Stall Speed (V_stall): %.2f m/s (%.2f km/h)\n', V_stall, V_stall*3.6);

% Cruise Speed (assuming flight at max L/D)
V_cruise = sqrt(2 * Weight_N / (rho * S * CL(idx_LD)));
fprintf('Cruise Speed (V_cruise): %.2f m/s (%.2f km/h)\n', V_cruise, V_cruise*3.6);

% Thrust required and Maximum Speed
T_W = 0.4;               % Thrust-to-weight ratio (Electric propulsion)
T_max = T_W * Weight_N;  % Max Thrust [N]

V_range = V_stall:0.5:40; % Speed range for analysis
CL_req = (2 * Weight_N) ./ (rho * S .* V_range.^2);
CD_req = CD0 + K .* CL_req.^2;
D_req = 0.5 * rho .* V_range.^2 .* S .* CD_req;
P_req = D_req .* V_range; % Power required
P_avail = T_max .* V_range; % Assuming constant thrust for simplicity

figure('Name', 'Performance Analysis');
subplot(1,2,1);
plot(V_range, D_req, 'b', 'LineWidth', 2); hold on;
plot(V_range, repmat(T_max, size(V_range)), 'r--', 'LineWidth', 2);
xlabel('Velocity [m/s]'); ylabel('Thrust / Drag [N]');
legend('Drag Required', 'Thrust Available');
title('Thrust vs Drag'); grid on;
ylim([0 T_max*1.5]);

subplot(1,2,2);
plot(V_range, P_req, 'b', 'LineWidth', 2); hold on;
plot(V_range, P_avail, 'r--', 'LineWidth', 2);
xlabel('Velocity [m/s]'); ylabel('Power [W]');
legend('Power Required', 'Power Available');
title('Power Required and Available'); grid on;

% Rate of Climb
RC = (P_avail - P_req) / Weight_N;
[RC_max, idx_RC] = max(RC);
fprintf('Max Rate of Climb: %.2f m/s at V = %.2f m/s\n', RC_max, V_range(idx_RC));

%% 4. Stability Analysis (Longitudinal Static & Dynamic)
disp('--- 4. Stability Analysis ---');

% Longitudinal Static Stability
% Center of Gravity and Aerodynamic Center
x_cg = 0.3 * c_mac;      % CG position at 30% MAC
x_ac_w = 0.25 * c_mac;   % Wing AC at 25% MAC
lt = 1.0;                % Tail moment arm [m]
S_t = 0.15 * S;          % Tail area [m^2]
V_H = (S_t * lt) / (S * c_mac); % Tail volume coefficient

% Derivatives
a_w = CL_alpha;          % Wing lift slope [1/rad]
a_t = 0.8 * a_w;         % Tail lift slope [1/rad] (with downwash effect)
eta_t = 0.9;             % Tail dynamic pressure ratio

C_L_alpha_total = a_w + a_t * eta_t * (S_t / S);
C_m_alpha = a_w * (x_cg - x_ac_w)/c_mac - a_t * V_H * eta_t;

fprintf('Tail Volume Coefficient (V_H): %.3f\n', V_H);
fprintf('C_m_alpha: %.4f [1/rad]\n', C_m_alpha);
if C_m_alpha < 0
    disp('Aircraft is Longitudinally STATICALLY STABLE (C_m_alpha < 0)');
else
    disp('Aircraft is Longitudinally STATICALLY UNSTABLE (C_m_alpha > 0)');
end

%% 5. Control Design (LQR Pitch Controller)
disp('--- 5. Control Design (Pitch LQR) ---');

% Simplified Longitudinal State-Space Model at Cruise
% States: x = [u; w; q; theta] (forward vel, vertical vel, pitch rate, pitch angle)
% Input: u = delta_e (elevator deflection)
u0 = V_cruise;

% Approximated Stability Derivatives for a 5kg UAV
Xu = -0.05; Xw = 0.05;  Xq = 0;    Xtheta = -g * cos(0);
Zu = -0.5;  Zw = -2.5;  Zq = u0;   Ztheta = -g * sin(0);
Mu = 0.05;  Mw = -0.15; Mq = -2.0; Mtheta = 0;
Xde = 0; Zde = -5.0; Mde = -15.0;

% State Space Matrices (A, B, C, D)
A = [Xu, Xw, Xq, Xtheta;
     Zu, Zw, Zq, Ztheta;
     Mu, Mw, Mq, Mtheta;
     0,  0,  1,  0];

B = [Xde; Zde; Mde; 0];
C = eye(4);
D = zeros(4,1);

% System Analysis
sys = ss(A, B, C, D);
disp('Open Loop Eigenvalues:');
disp(eig(A));
% Phugoid and Short Period modes are represented by the eigenvalues

% LQR Design
% Q matrix penalizes the states (we want to tightly control theta and q)
Q = diag([0.1, 0.1, 10, 100]);
% R matrix penalizes elevator effort
R = 1;

[K_lqr, S_lqr, e_lqr] = lqr(A, B, Q, R);

fprintf('LQR Feedback Gains K: [%.4f, %.4f, %.4f, %.4f]\n', K_lqr);
disp('Closed Loop Eigenvalues (A - B*K):');
disp(eig(A - B*K_lqr));

% Simulation of Initial Condition Response (Pitch displacement)
sys_cl = ss(A - B*K_lqr, B, C, D);
t = 0:0.01:10;
x0 = [0; 0; 0; 0.1]; % Initial pitch angle of 0.1 rad (~5.7 deg)
[Y, T_sim, X] = initial(sys_cl, x0, t);

figure('Name', 'LQR Pitch Control Response');
subplot(2,1,1);
plot(T_sim, X(:,4) * 180/pi, 'b', 'LineWidth', 2);
xlabel('Time [s]'); ylabel('\theta (Pitch Angle) [deg]');
title('Closed-Loop Pitch Angle Response'); grid on;

subplot(2,1,2);
plot(T_sim, X(:,3) * 180/pi, 'r', 'LineWidth', 2);
xlabel('Time [s]'); ylabel('q (Pitch Rate) [deg/s]');
title('Closed-Loop Pitch Rate Response'); grid on;

disp('UAV Design, Analysis, and Control Script Execution Completed.');

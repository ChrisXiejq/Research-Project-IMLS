function ok = precarla_validate_uk_give_way_matlab()
%PRECARLA_VALIDATE_UK_GIVE_WAY_MATLAB MATLAB sanity check for the UK give-way scenario.
%
% This mirrors the Python pre-CARLA validation. It intentionally checks only
% scenario geometry and simplified timing, not CARLA dynamics or SMPC solving.

repoRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
scenarioPath = fullfile(repoRoot, 'core', 'scripts', 'carla', 'scenarios', 'scenario_uk_give_way.json');

scenarioText = fileread(scenarioPath);
scenario = jsondecode(scenarioText);

intersectionPath = fullfile(fileparts(scenarioPath), scenario.carla_params.intersection_csv_loc);
intersection = loadIntersection(intersectionPath);

ego = getVehicle(scenario.vehicle_params, 'ego');
target = getVehicle(scenario.vehicle_params, 'target');

egoPath = buildPath(scenario, intersection, ego);
targetPath = buildPath(scenario, intersection, target);

conflictPoint = firstPolylineIntersection(egoPath, targetPath);
if any(isnan(conflictPoint))
    conflictPoint = nearestPolylineMidpoint(egoPath, targetPath);
end

egoDist = distanceAlongPathToPoint(egoPath, conflictPoint);
targetDist = distanceAlongPathToPoint(targetPath, conflictPoint);
egoTtc = egoDist / max(double(ego.nominal_speed), 1e-6);
targetTtc = targetDist / max(double(target.nominal_speed), 1e-6);
timeGap = egoTtc - targetTtc;

noYieldMinDistance = simulateMinDistance(egoPath, targetPath, double(ego.nominal_speed), double(target.nominal_speed), 0.0);
egoWait = max(0.0, 2.0 - timeGap);
giveWayMinDistance = simulateMinDistance(egoPath, targetPath, double(ego.nominal_speed), double(target.nominal_speed), egoWait);

checks = {};
checks{end+1} = makeCheck(strcmpi(scenario.carla_params.traffic_control, 'unsignalised'), 'scenario declares unsignalised traffic control');
checks{end+1} = makeCheck(strcmpi(scenario.carla_params.side_of_road, 'left'), 'scenario declares UK left-hand traffic');
checks{end+1} = makeCheck(~logical(scenario.prediction_params.render_traffic_lights), 'traffic lights are not rendered for the default predictor input');
checks{end+1} = makeCheck(~logical(ego.obey_traffic_lights) && ~logical(target.obey_traffic_lights), 'ego and target do not obey traffic-light overrides');
checks{end+1} = makeCheck(strcmp(ego.traffic_role, 'turning_give_way_vehicle'), 'ego is marked as the turning give-way vehicle');
checks{end+1} = makeCheck(strcmp(target.traffic_role, 'priority_oncoming_straight'), 'target is marked as the priority oncoming straight vehicle');
checks{end+1} = makeCheck(targetTtc < egoTtc, 'target reaches the conflict point before ego');
checks{end+1} = makeCheck(timeGap > 0.0 && timeGap < 2.0, 'nominal timing creates a meaningful give-way interaction');
checks{end+1} = makeCheck(giveWayMinDistance > noYieldMinDistance, 'simple give-way delay increases the minimum separation');

fprintf('MATLAB Pre-CARLA UK give-way validation\n');
fprintf('======================================\n');
ok = true;
for i = 1:numel(checks)
    if checks{i}.ok
        fprintf('PASS: %s\n', checks{i}.label);
    else
        fprintf('FAIL: %s\n', checks{i}.label);
        ok = false;
    end
end

fprintf('\nConflict timing\n');
fprintf('- conflict_point: (%.2f, %.2f) m\n', conflictPoint(1), conflictPoint(2));
fprintf('- ego_distance_to_conflict: %.2f m\n', egoDist);
fprintf('- target_distance_to_conflict: %.2f m\n', targetDist);
fprintf('- ego_ttc: %.2f s\n', egoTtc);
fprintf('- target_ttc: %.2f s\n', targetTtc);
fprintf('- ego_minus_target_ttc: %.2f s\n', timeGap);
fprintf('- no_yield_min_distance: %.2f m\n', noYieldMinDistance);
fprintf('- give_way_min_distance: %.2f m\n', giveWayMinDistance);

if ~ok
    error('MATLAB pre-CARLA validation failed.');
end
end

function check = makeCheck(ok, label)
check = struct('ok', logical(ok), 'label', label);
end

function vehicle = getVehicle(vehicleParams, role)
for i = 1:numel(vehicleParams)
    if strcmp(vehicleParams(i).role, role)
        vehicle = vehicleParams(i);
        return;
    end
end
error('Vehicle role not found: %s', role);
end

function intersection = loadIntersection(path)
fid = fopen(path, 'r');
if fid < 0
    error('Could not open intersection CSV: %s', path);
end
cleaner = onCleanup(@() fclose(fid));
rows = {};
while true
    line = fgetl(fid);
    if ~ischar(line)
        break;
    end
    if contains(line, '#') || isempty(strtrim(line))
        continue;
    end
    values = sscanf(line, '%f,%f,%f,%f,%f,%f');
    rows{end+1} = values(:)'; %#ok<AGROW>
end
intersection = cell2mat(rows');
end

function path = buildPath(scenario, intersection, vehicle)
startIdx = double(vehicle.intersection_start_node_idx) + 1;
goalIdx = double(vehicle.intersection_goal_node_idx) + 1;
sideOfRoad = scenario.carla_params.side_of_road;

startPose = intersection(startIdx, 1:3);
goalPose = intersection(goalIdx, 4:6);

startPoint = transformPose(startPose, double(vehicle.start_left_offset), getFieldDefault(vehicle, 'start_longitudinal_offset', 0.0), sideOfRoad);
goalPoint = transformPose(goalPose, double(vehicle.goal_left_offset), getFieldDefault(vehicle, 'goal_longitudinal_offset', 0.0), sideOfRoad);

if startIdx == goalIdx
    path = [startPoint; goalPoint];
else
    center = intersectionCenter(intersection);
    path = [startPoint; center; goalPoint];
end
end

function value = getFieldDefault(s, name, defaultValue)
if isfield(s, name)
    value = double(s.(name));
else
    value = defaultValue;
end
end

function point = transformPose(pose, leftOffset, longitudinalOffset, sideOfRoad)
yawRad = deg2rad(double(pose(3)));
x = double(pose(1)) + longitudinalOffset * cos(yawRad);
y = double(pose(2)) + longitudinalOffset * sin(yawRad);

if strcmpi(sideOfRoad, 'left')
    lateralSign = 1.0;
else
    lateralSign = -1.0;
end
lateralYaw = yawRad + lateralSign * pi / 2.0;
x = x + leftOffset * cos(lateralYaw);
y = y + leftOffset * sin(lateralYaw);
point = [x, y];
end

function center = intersectionCenter(intersection)
xs = [intersection(:, 1); intersection(:, 4)];
ys = [intersection(:, 2); intersection(:, 5)];
center = [mean(xs), mean(ys)];
end

function d = pointDistance(a, b)
d = hypot(a(1) - b(1), a(2) - b(2));
end

function len = polylineLength(path)
len = 0.0;
for i = 1:size(path, 1)-1
    len = len + pointDistance(path(i, :), path(i+1, :));
end
end

function point = pathPointAtDistance(path, s)
if s <= 0.0
    point = path(1, :);
    return;
end
remaining = s;
for i = 1:size(path, 1)-1
    a = path(i, :);
    b = path(i+1, :);
    segLen = pointDistance(a, b);
    if segLen <= 1e-9
        continue;
    end
    if remaining <= segLen
        alpha = remaining / segLen;
        point = a + alpha * (b - a);
        return;
    end
    remaining = remaining - segLen;
end
point = path(end, :);
end

function sBest = distanceAlongPathToPoint(path, point)
sBest = 0.0;
bestDist = inf;
sPrefix = 0.0;
for i = 1:size(path, 1)-1
    a = path(i, :);
    b = path(i+1, :);
    ab = b - a;
    segLenSq = dot(ab, ab);
    if segLenSq <= 1e-12
        continue;
    end
    ap = point - a;
    alpha = max(0.0, min(1.0, dot(ap, ab) / segLenSq));
    proj = a + alpha * ab;
    d = pointDistance(proj, point);
    if d < bestDist
        bestDist = d;
        sBest = sPrefix + alpha * sqrt(segLenSq);
    end
    sPrefix = sPrefix + sqrt(segLenSq);
end
end

function point = firstPolylineIntersection(pathA, pathB)
point = [nan, nan];
for i = 1:size(pathA, 1)-1
    for j = 1:size(pathB, 1)-1
        candidate = segmentIntersection(pathA(i, :), pathA(i+1, :), pathB(j, :), pathB(j+1, :));
        if ~any(isnan(candidate))
            point = candidate;
            return;
        end
    end
end
end

function point = segmentIntersection(a, b, c, d)
point = [nan, nan];
r = b - a;
s = d - c;
denom = r(1) * s(2) - r(2) * s(1);
if abs(denom) < 1e-9
    return;
end
qmp = c - a;
t = (qmp(1) * s(2) - qmp(2) * s(1)) / denom;
u = (qmp(1) * r(2) - qmp(2) * r(1)) / denom;
if t >= 0.0 && t <= 1.0 && u >= 0.0 && u <= 1.0
    point = a + t * r;
end
end

function point = nearestPolylineMidpoint(pathA, pathB)
bestA = pathA(1, :);
bestB = pathB(1, :);
bestDist = inf;
samples = 80;
lenA = polylineLength(pathA);
lenB = polylineLength(pathB);
for i = 0:samples
    pa = pathPointAtDistance(pathA, lenA * i / samples);
    for j = 0:samples
        pb = pathPointAtDistance(pathB, lenB * j / samples);
        d = pointDistance(pa, pb);
        if d < bestDist
            bestDist = d;
            bestA = pa;
            bestB = pb;
        end
    end
end
point = (bestA + bestB) / 2.0;
end

function minDist = simulateMinDistance(egoPath, targetPath, egoSpeed, targetSpeed, egoWait)
dt = 0.05;
horizon = 8.0;
minDist = inf;
for k = 0:floor(horizon / dt)
    t = k * dt;
    egoS = max(0.0, t - egoWait) * egoSpeed;
    targetS = t * targetSpeed;
    egoPos = pathPointAtDistance(egoPath, egoS);
    targetPos = pathPointAtDistance(targetPath, targetS);
    minDist = min(minDist, pointDistance(egoPos, targetPos));
end
end

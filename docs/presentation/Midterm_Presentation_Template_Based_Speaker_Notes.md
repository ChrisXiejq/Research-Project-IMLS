# Template-Based Midterm Presentation Speaker Notes

## Slide 1
I am teaching a simulated self-driving car how to cross a busy junction safely when another car may move in different ways.

## Slide 2
This is about safe decision-making. The car must choose when to go, but it cannot know exactly what other cars will do.

## Slide 3
The key problem is uncertainty. A single predicted future is not enough, so the car should think about several possible futures.

## Slide 4
The car should not be too brave, too scared, or too uncomfortable. It should balance safety, progress, and smoothness.

## Slide 5
The paper idea is to connect prediction with control: see several futures, then choose a safer action.

## Slide 6
My hypothesis is that using several possible futures should help the car plan more safely than weaker baselines.

## Slide 7
My experiment pipeline is now working: scenario setup, CARLA simulation, prediction, planner, action, logs, and metrics.

## Slide 8
The main risks are simulator time, planner failures, messy paths, and not enough tests. I handle them with small pilots and debug logs.

## Slide 9
The pipeline works and early results are promising, but the project still needs cleaner paths, fewer failures, and more evaluation.

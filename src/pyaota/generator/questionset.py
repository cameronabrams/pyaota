# Author: Cameron F. Abrams <cfa22@drexel.edu>

"""
Question set management for pyaota
"""

import shutil
import yaml
import logging

logger = logging.getLogger(__name__)
import random
from pathlib import Path

class QuestionSet:
    """
    Class to manage a set of questions loaded from YAML files.
    Supports loading from multiple files, organizing by topic,
    and selecting random subsets of questions.
    """
    def __init__(self, question_banks: list[str] = []):
        self.data = {}
        self.image_dirs: list[Path] = []
        for yaml_file in question_banks:
            yaml_path = Path(yaml_file)
            with open(yaml_file, "r", encoding="utf-8") as f:
                file_data = yaml.safe_load(f)
                if not self.data:
                    self.data = file_data
                else:
                    # Merge questions from multiple files
                    self.data["questions"].extend(file_data.get("questions", []))
                    for topic in file_data.get("topics", []):
                        if topic not in self.data.get("topics", []):
                            self.data.setdefault("topics", []).append(topic)
            # Track images/ directory alongside each YAML file
            img_dir = yaml_path.parent / "images"
            if img_dir.is_dir() and img_dir not in self.image_dirs:
                self.image_dirs.append(img_dir)

        self.topics_from_yaml = self.data.get("topics", [])
        self.raw_question_list = self.data.get("questions", [])
        # convert id numbers to integers if possible
        for q in self.raw_question_list:
            if "id" in q:
                try:
                    q["id"] = int(q["id"])
                except (ValueError, TypeError):
                    pass
        self.questions_by_topic = {}
        for q in self.raw_question_list:
            topic = q.get("topic", "General")
            if topic not in self.questions_by_topic:
                self.questions_by_topic[topic] = []
            self.questions_by_topic[topic].append(q)

        self.apparent_topics = list(self.questions_by_topic.keys())
        for topic in self.apparent_topics:
            logger.debug(f"Topic '{topic}': {len(self.questions_by_topic[topic])} questions available.")

    def copy_images_to(self, dest_dir: Path):
        """Copy all question bank images into *dest_dir*/images/.

        Only copies if any question bank had an ``images/`` directory
        next to its YAML file.
        """
        if not self.image_dirs:
            return
        target = Path(dest_dir) / "images"
        target.mkdir(parents=True, exist_ok=True)
        count = 0
        for img_dir in self.image_dirs:
            if img_dir.resolve() == target.resolve():
                continue
            for img in img_dir.iterdir():
                if img.is_file():
                    shutil.copy2(img, target / img.name)
                    count += 1
        if count:
            logger.debug(f"Copied {count} image(s) to {target}")

    def get_random_selection(self, 
            num_questions: int, 
            topics_order: list[str] | None = None, 
            seed: int = 0, 
            rng: callable = None, 
            shuffle: bool = True, 
            shuffle_choices: bool = True) -> list[dict]:
        """
        Selects a random set of questions from the question set.

        Parameters
        ----------
        num_questions : int
            Total number of questions to select.
        topics_order : list[str] | None
            List of topics in the order to select questions from. 
            If None, use all topics in arbitrary order.
        seed : int
            Seed for the random number generator.
        rng : callable
            Random number generator instance (e.g., random.Random).
        shuffle : bool
            If True, shuffle the selected questions before returning.
        shuffle_choices : bool
            If True, shuffle the choices within each multiple-choice question.

        Returns
        -------
        list[dict]
            List of selected question dictionaries.
        """

        if rng is None:
            logger.debug(f'Using seed {seed} for question selection; no RNG provided.')
            rng = random.Random(seed)

        selected_questions: list[dict] = []
        auto_topics = topics_order is None or topics_order == []
        if auto_topics:
            ordered_topics = list(self.questions_by_topic.keys())
        else:
            # Only include topics that actually appear in questions_by_topic
            ordered_topics = [t for t in topics_order if t in self.questions_by_topic]

        logger.debug(f'Using topic order: {ordered_topics}')

        # Compute per-topic allocations. Process the most-constrained topics
        # first (fewest available questions) so that any shortfall is
        # redistributed to topics that have more questions, keeping the
        # total exactly equal to num_questions.
        topics_by_avail = sorted(
            ordered_topics,
            key=lambda t: len(self.questions_by_topic.get(t, [])),
        )
        allocations: dict[str, int] = {}
        remaining_need = num_questions
        for i, topic in enumerate(topics_by_avail):
            remaining_topics = len(topics_by_avail) - i
            desired = remaining_need // remaining_topics
            available = len(self.questions_by_topic.get(topic, []))
            actual = min(desired, available)
            allocations[topic] = actual
            remaining_need -= actual
            logger.debug(
                f"Allocating {actual} (wanted {desired}, available {available}) "
                f"from topic '{topic}'; {remaining_need} still needed."
            )

        if remaining_need > 0:
            total_available = sum(len(self.questions_by_topic.get(t, [])) for t in ordered_topics)
            raise ValueError(
                f"Requested {num_questions} questions but only {total_available} "
                f"available across {len(ordered_topics)} topic(s)."
            )

        # Sample questions in the original topic order
        for topic in ordered_topics:
            n = allocations.get(topic, 0)
            if n <= 0:
                continue
            pool = self.questions_by_topic.get(topic, [])
            chosen = list(pool) if n == len(pool) else rng.sample(pool, n)
            selected_questions.extend(chosen)
            logger.debug(f"Selected {len(chosen)}/{len(pool)} questions from topic '{topic}'.")
            selected_ids = [q.get("id", "N/A") for q in chosen]
            logger.debug(f"  Selected question IDs: {selected_ids}")
            logger.debug(f"  Total selected so far: {len(selected_questions)}")
            logger.debug(f"  Selected question IDs so far: {[q.get('id', 'N/A') for q in selected_questions]}")

        if shuffle:
            logger.debug('Shuffling selected questions.')
            rng.shuffle(selected_questions)

        if shuffle_choices:
            # shuffle choices only for multiple-choice questions
            logger.debug('Shuffling choices within multiple-choice questions.')
            for question in selected_questions:
                if not question['type'] == 'mcq':
                    continue
                logger.debug(f'Shuffling choices for question ID {question.get("id", "N/A")}')
                choices = question.get("choices", [])
                choice_keys = [str(c.get("key", "")).strip() for c in choices if c.get("key", "") not in (None, "")]
                correct_old_key = str(question.get("correct", "")).strip()
                new_choice_keys = choice_keys.copy()
                rng.shuffle(new_choice_keys)
                for old, new in zip(choice_keys, new_choice_keys):
                    if old == correct_old_key:
                        question["correct"] = new
                        break
                # now, re-key the choices according to new_choice_keys
                for i, c in enumerate(choices):
                    c["key"] = new_choice_keys[i]
                # sort choices by new key
                choices.sort(key=lambda x: x.get("key", ""))
                question["choices"] = choices

        logger.debug(f'Total selected questions: {len(selected_questions)}')
        logger.debug(f'Selected question IDs: {[q.get("id", "N/A") for q in selected_questions]}')
        return selected_questions


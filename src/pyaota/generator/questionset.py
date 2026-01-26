# Author: Cameron F. Abrams <cfa22@drexel.edu>

"""
Question set management for pyaota
"""

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
        for yaml_file in question_banks:
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
        if topics_order is None or topics_order == []:
            ordered_topics = list(self.questions_by_topic.keys())
        else:
            # Only include topics that actually appear in questions_by_topic
            ordered_topics = [t for t in topics_order if t in self.questions_by_topic]    

        logger.debug(f'Using topic order: {ordered_topics}')

        for topic in ordered_topics:
            desired = num_questions // len(ordered_topics)
            if desired <= 0:
                continue
            
            pool = self.questions_by_topic.get(topic, [])
            available = len(pool)
            logger.debug(f"Selecting {desired} questions from topic '{topic}' with {available} available.")
            if desired > available:
                raise ValueError(
                    f"Requested {desired} questions for topic '{topic}' "
                    f"but only {available} available."
                )

            if desired == available:
                # No need to sample, but we still want deterministic behavior
                chosen = list(pool)
            else:
                # Sample without replacement
                chosen = rng.sample(pool, desired)

            selected_questions.extend(chosen)
            logger.debug(f"Selected {len(chosen)}/{len(pool)} questions from topic '{topic}'.")
            # show ID numbers of selected questions
            selected_ids = [q.get("id", "N/A") for q in chosen]
            logger.debug(f"  Selected question IDs: {selected_ids}")
            logger.debug(f"  Total selected so far: {len(selected_questions)}")
            logger.debug(f" Selected question IDs so far: {[q.get('id', 'N/A') for q in selected_questions]}")
        # if we have not yet selected enough questions (due to rounding down), fill in from the start
        while len(selected_questions) < num_questions:
            for topic in ordered_topics:
                if len(selected_questions) >= num_questions:
                    break
                pool = self.questions_by_topic.get(topic, [])
                available = len(pool)
                logger.debug(f"Filling in from topic '{topic}' with {available} available.")
                # select one additional question from this topic
                remaining_pool = [q for q in pool if q not in selected_questions]
                if not remaining_pool:
                    logger.debug(f"No remaining questions to select from topic '{topic}'.")
                    continue
                chosen = rng.choice(remaining_pool)
                selected_questions.append(chosen)
                logger.debug(f"Added question ID {chosen.get('id', 'N/A')} from topic '{topic}'.")
                logger.debug(f" Total selected so far: {len(selected_questions)}")
                logger.debug(f" Selected question IDs so far: {[q.get('id', 'N/A') for q in selected_questions]}")

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


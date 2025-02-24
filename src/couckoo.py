import argparse
import logging
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from ImageProcessor import ImageProcessor


class LSHProcessor:
    """
    Locality Sensitive Hashing Processor for image similarity detection.
    """

    def __init__(self, hash_size: int, bands: int):
        """
        Initialize LSHProcessor with hash size and number of bands.

        Args:
            hash_size (int): Size of the image hash.
            bands (int): Number of bands for LSH.
        """
        self.hash_size = hash_size
        self.bands = bands
        self.rows = hash_size**2 // bands
        self.hash_buckets_list = [{} for _ in range(bands)]
        self.signatures: Dict[str, np.ndarray] = {}
        self.labels: Dict[str, int] = {}
        self.label_counter = 0
        self.similarity_scores: List[Tuple[str, str, float]] = []

    def add_signature(self, file_path: str, signature: np.ndarray):
        """
        Add image signature to LSH buckets.

        Args:
        file_path (str): File path of the image.
        signature (np.ndarray): Image signature as Numpy n-dimensional array.
        """
        if signature is None:
            return
        self.signatures[file_path] = np.packbits(signature)

        for i in range(self.bands):
            signature_band = signature[i * self.rows: (i + 1) * self.rows]
            signature_band_bytes = signature_band.tobytes()
            if signature_band_bytes not in self.hash_buckets_list[i]:
                self.hash_buckets_list[i][signature_band_bytes] = []
            self.hash_buckets_list[i][signature_band_bytes].append(file_path)

    def calculate_similarity(self, pair: Tuple[str, str]) -> Tuple[str, str, float]:
        """
        Calculate the similarity between two images using hamming distance.

        Args:
            pair (tuble): images to cal similarity for.

        Returns:
            images and the similarity score between them on a (0-1) scale,
            1 being highly similar
        """
        img_a, img_b = pair
        try:
            hd = np.count_nonzero(
                np.unpackbits(self.signatures[img_a])
                != np.unpackbits(self.signatures[img_b])
            )
            similarity = (self.hash_size**2 - hd) / self.hash_size**2
            return img_a, img_b, similarity
        except KeyError:
            logging.error(f"Signatures not found for pair: {pair}")
            return img_a, img_b, 0.0

    def process_similarities(
        self, threshold: float, collect_scores: bool = False
    ) -> None:
        """
        Process and assign labels or collect similarity scores based on threshold.

        Args:
            threshold (float): Similarity threshold to consider images as similar.
            collect_scores (bool): Flag to indicate if similarity scores should be collected.
        """
        for hash_buckets in self.hash_buckets_list:
            for matched_imgs in hash_buckets.values():
                if len(matched_imgs) > 1:
                    for image_a, image_b in zip(matched_imgs, matched_imgs[1:]):
                        img_a, img_b, similarity = self.calculate_similarity(
                            (image_a, image_b)
                        )
                        if similarity >= threshold:
                            if img_a not in self.labels:
                                self.labels[img_a] = self.label_counter
                                self.label_counter += 1
                            if img_b not in self.labels:
                                self.labels[img_b] = self.labels[img_a]

                            if collect_scores:
                                self.similarity_scores.append(
                                    (img_a, img_b, similarity)
                                )

    def assign_labels(self, threshold: float) -> Dict[str, int]:
        """
        Assign integer labels to images, with similar images above threshold having same label.

        Args:
            threshold (float): Similarity threshold to consider images as similar.

        Returns:
            Dict[str, int]: Mapping of image file paths to their assigned labels.
        """
        self.process_similarities(threshold)
        self._assign_labels_remaining_images()
        return self.labels

    def _assign_labels_remaining_images(self) -> None:
        """Assign labels to remaining images (not part of any near-duplicate pair)"""

        for file_path in self.signatures.keys():
            if file_path not in self.labels:
                self.labels[file_path] = self.label_counter
                self.label_counter += 1

    def get_similarity_scores(self, threshold: float) -> List[Tuple[str, str, float]]:
        """
        Updates similar images with their similarity score.

        Args:
            threshold (float): Similarity threshold to consider images as similar.

        """
        self.process_similarities(threshold, collect_scores=True)
        return self.similarity_scores


# helper functions
def get_image_files(input_dir: str) -> List[str]:
    """
    Retrieve image files from a directory.

    Args:
        input_dir (str): Directory containing images.

    Returns:
        List[str]: List of image file paths.
    """
    image_extensions = (".png", ".jpg", ".jpeg")
    try:
        file_list = [
            os.path.join(input_dir, f)
            for f in os.listdir(input_dir)
            if f.lower().endswith(image_extensions)
        ]
        return file_list
    except FileNotFoundError:
        logging.error(f"Directory not found: {input_dir}")
        raise ValueError(f"Directory {input_dir} does not exist")


def process_images(
    hash_size, bands, image_processor: ImageProcessor, file_list: List[str]
) -> LSHProcessor:
    """
    Process images and calculate their signatures using ImageProcessor.

    Args:
        image_processor (ImageProcessor): Instance of ImageProcessor.
        file_list (List[str]): List of image file paths.

    Returns:
        LSHProcessor: Instance of LSHProcessor populated with image signatures.
    """
    lsh_processor = LSHProcessor(hash_size, bands)
    for file_path in file_list:
        signature = image_processor.calculate_signature(file_path)
        lsh_processor.add_signature(file_path, signature)
    return lsh_processor


def find_duplicates(
    input_dir: str, threshold: float, hash_size: int, bands: int, gen_socres: bool
) -> Tuple[Dict[str, int], List[Tuple[str, str, float]]]:
    """
    Find near-duplicate images within a directory using Locality Sensitive Hashing.

    Args:
        input_dir (str): Directory containing images.
        threshold (float): Similarity threshold.
        hash_size (int): Size of the image hash.
        bands (int): Number of bands for LSH.

    Returns:
        Dict[str, int]: Dictionary of image file paths and their assigned labels.
    """
    image_processor = ImageProcessor(hash_size)
    similarity_scores = []

    try:
        file_list = get_image_files(input_dir)
        if not file_list:
            raise ValueError(f"No valid images found in directory {input_dir}")

        lsh_processor = process_images(hash_size, bands, image_processor, file_list)
        labels = lsh_processor.assign_labels(threshold)

        if gen_socres:
            similarity_scores = lsh_processor.get_similarity_scores(threshold)

        return labels, similarity_scores

    except ValueError as ve:
        logging.error(str(ve))
        return {}, []


def get_results(
    input_dir: str, threshold: float, hash_size: int, bands: int, gen_socres: bool
) -> None:
    """
    outputs a  csv of file names and labels

    Parameters
    ----------
    input_dir (str) : images directory path
    threshold (float) : similarity threshold
    hash_size (int) : hash_size
    bands (int) : band size
    """

    output_file = "results/labels.csv"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    labels, similarity_scores = find_duplicates(
        input_dir, threshold, hash_size, bands, gen_socres
    )
    df = pd.DataFrame(list(labels.items()), columns=["filename", "label"])
    df.sort_values("label").to_csv(output_file)

    if gen_socres:
        generate_similarity_scores(
            similarity_scores,
        )


def generate_similarity_scores(similarity_scores: List[Tuple[str, str, float]]) -> None:
    """
    outputs a  csv of  images file paths and similarity scores
    

    """
    scores_file = "results/scores.csv"
    os.makedirs(os.path.dirname(scores_file), exist_ok=True)
    df_scores = pd.DataFrame(
        similarity_scores, columns=["imageA", "imageB", "similarity"]
    )
    df_scores.to_csv(scores_file, index=False)


def main(argv):
    # Argument parser
    parser = argparse.ArgumentParser(
        description="Efficient detection of near-duplicate images using locality sensitive hashing"
    )
    args = parser.parse_args()
    parser.add_argument(
        "-i",
        "--input_dir",
        type=str,
        default="data",
        help="Directory containing image files.",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=0.8,
        help="Threshold for near duplicates.",
    )
    parser.add_argument(
        "-s",
        "--hash_size",
        type=int,
        default=16,
        help="Size of the hash.",
    )
    parser.add_argument("-b", "--bands", type=int, default=16, help="Number of bands.")
    parser.add_argument(
        "-c",
        "--scores",
        type=bool,
        default=True,
        help="generate a duplicates.csv file with duplicated images and the similarity score.",
    )
    parser.add_argument(
        "-l",
        "--gen_lables",
        type=bool,
        default=True,
        help="genrate results.csv file with all near duplicate images having the same label.",
    )

    args = parser.parse_args()
    input_dir = args.input_dir
    threshold = args.threshold
    hash_size = args.hash_size
    bands = args.bands
    show_similarity_scores = args.scores

    get_results(input_dir, threshold, hash_size, bands, show_similarity_scores)


if __name__ == "__main__":
    main(sys.argv)

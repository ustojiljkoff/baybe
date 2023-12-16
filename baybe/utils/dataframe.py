"""Dataframe utilities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Iterable, List, Literal, Optional, Tuple, Union

import numpy as np
import pandas as pd
import torch
from torch import Tensor

from baybe.targets.enum import TargetMode
from baybe.utils.numeric import DTypeFloatNumpy, DTypeFloatTorch

if TYPE_CHECKING:
    from baybe.campaign import Campaign
    from baybe.parameters import Parameter

# Logging
_logger = logging.getLogger(__name__)


def to_tensor(*dfs: pd.DataFrame) -> Union[Tensor, Iterable[Tensor]]:
    """Convert a given set of dataframes into tensors (dropping all indices).

    Args:
        *dfs: A set of dataframes

    Returns:
        The provided dataframe(s), transformed into Tensor(s)
    """
    # FIXME This function seems to trigger a problem when some columns in either of
    #  the dfs have a dtype other than int or float (e.g. object, bool). This can
    #  weirdly happen, even if all values are numeric, e.g. when a target column is
    #  looked up from a df in simulation, it can have dtype object even if it's all
    #  floats. As a simple fix (this seems to be the most reasonable place to take
    #  care of this) df.values has been changed to df.values.astype(float),
    #  even though this seems like double casting here.
    out = (
        torch.from_numpy(df.values.astype(DTypeFloatNumpy)).to(DTypeFloatTorch)
        for df in dfs
    )
    if len(dfs) == 1:
        out = next(out)
    return out


def add_fake_results(
    data: pd.DataFrame,
    campaign: Campaign,
    good_reference_values: Optional[Dict[str, list]] = None,
    good_intervals: Optional[Dict[str, Tuple[float, float]]] = None,
    bad_intervals: Optional[Dict[str, Tuple[float, float]]] = None,
) -> None:
    """Add fake results to a dataframe which was the result of a BayBE recommendation.

    It is possible to specify "good" values, which will be given a better
    target value. With this, the algorithm can be driven towards certain optimal values
    whilst still being random. Useful for testing. Note that this does not return a
    new dataframe and that the dataframe is changed in-place.

    Args:
        data: Output of the ``recommend`` function of a ``Campaign``, see
            :func:`baybe.campaign.Campaign.recommend`.
        campaign: The corresponding campaign, providing configuration, targets, etc.
        good_reference_values: A dictionary containing parameter names (= dict keys) and
            respective parameter values (= dict values) that specify what will be
            considered good parameter settings. Conditions for different parameters are
            connected via "and" logic, i.e. the targets will only get good values when
            all parameters have good reference values.
        good_intervals: A dictionary containing target names (= dict keys) and
            respective "good" target value ranges (= dict values) in the form of
            2-tuples. Each target will be assigned a random value in its respective
            target range whenever the corresponding parameters meet the conditions
            specified through ``good_reference_values``.
        bad_intervals: Analogous to ``good_intervals`` but covering the cases where
            the parameters lie outside the conditions specified through
            ``good_reference_values``.

    Raises:
        ValueError: If good values for a parameter were specified, but this parameter
            is not part of the dataframe.
        ValueError: If the target mode is unrecognized when trying to add fake values.
        TypeError: If the entries in ``good_reference_values`` are not lists.
    """
    # Per default, there are no reference values for good parameters
    if good_reference_values is None:
        good_reference_values = {}

    # Validate input
    for param, vals in good_reference_values.items():
        if param not in data.columns:
            raise ValueError(
                f"When adding fake results you specified good "
                f"values for the parameter '{param}' but this "
                f"parameter is not in the dataframe."
            )
        if not isinstance(vals, list):
            raise TypeError(
                f"Entries in parameter 'good_reference_values' "
                f"(which is a dictionary) must be lists, but you "
                f"provided {vals}."
            )

    # Set defaults for good intervals
    if good_intervals is None:
        good_intervals = {}
        for target in campaign.targets:
            if target.mode is TargetMode.MAX:
                lbound = target.bounds.lower if np.isfinite(target.bounds.lower) else 66
                ubound = (
                    target.bounds.upper if np.isfinite(target.bounds.upper) else 100
                )
                interv = (lbound, ubound)
            elif target.mode is TargetMode.MIN:
                lbound = target.bounds.lower if np.isfinite(target.bounds.lower) else 0
                ubound = target.bounds.upper if np.isfinite(target.bounds.upper) else 33
                interv = (lbound, ubound)
            elif target.mode is TargetMode.MATCH:
                lbound = target.bounds.lower if np.isfinite(target.bounds.lower) else 0
                ubound = (
                    target.bounds.upper if np.isfinite(target.bounds.upper) else 100
                )
                interv = (
                    lbound + 0.4 * (ubound - lbound),
                    lbound + 0.6 * (ubound - lbound),
                )
            else:
                raise ValueError(
                    "Unrecognized target mode when trying to add fake values."
                )
            good_intervals[target.name] = interv

    # Set defaults for bad intervals
    if bad_intervals is None:
        bad_intervals = {}
        for target in campaign.targets:
            if target.mode is TargetMode.MAX:
                lbound = target.bounds.lower if np.isfinite(target.bounds.lower) else 0
                ubound = target.bounds.upper if np.isfinite(target.bounds.upper) else 33
                interv = (lbound, ubound)
            elif target.mode is TargetMode.MIN:
                lbound = target.bounds.lower if np.isfinite(target.bounds.lower) else 66
                ubound = (
                    target.bounds.upper if np.isfinite(target.bounds.upper) else 100
                )
                interv = (lbound, ubound)
            elif target.mode is TargetMode.MATCH:
                lbound = target.bounds.lower if np.isfinite(target.bounds.lower) else 0
                ubound = (
                    target.bounds.upper if np.isfinite(target.bounds.upper) else 100
                )
                interv = (
                    # Take as bad values the interval above the good interval
                    lbound + 0.6 * (ubound - lbound),
                    lbound + 1.2 * (ubound - lbound),
                )
            else:
                raise ValueError(
                    "Unrecognized target mode when trying to add fake values."
                )
            bad_intervals[target.name] = interv

    # Add the fake data for each target
    for target in campaign.targets:
        # Add bad values
        data[target.name] = np.random.uniform(
            bad_intervals[target.name][0], bad_intervals[target.name][1], len(data)
        )

        # Create masks that identify locations where to place good values
        masks = []
        for param, vals in good_reference_values.items():
            mask = data[param].isin(vals)
            masks.append(mask)

        # Overwrite bad values with good ones using the computed masks
        if len(masks) > 0:
            final_mask = pd.concat(masks, axis=1).all(axis=1)
            data.loc[final_mask, target.name] = np.random.uniform(
                good_intervals[target.name][0],
                good_intervals[target.name][1],
                final_mask.sum(),
            )


def add_parameter_noise(
    data: pd.DataFrame,
    parameters: Iterable[Parameter],
    noise_type: Literal["absolute", "relative_percent"] = "absolute",
    noise_level: float = 1.0,
) -> None:
    """Apply uniform noise to the parameter values of a recommendation frame.

    The noise can be additive or multiplicative.
    This can be used to simulate experimental noise or imperfect user input containing
    numerical parameter values that differ from the recommendations. Note that the
    dataframe is modified in-place, and that no new dataframe is returned.

    Args:
        data: Output of the ``recommend`` function of a ``Campaign`` object, see
            :func:`baybe.campaign.Campaign.recommend`.
        parameters: The parameters for which the values shall be corrupted.
        noise_type: Defines whether the noise should be additive or multiplicative.
        noise_level: Level/magnitude of the noise. Must be provided as numerical value
            for noise type ``absolute`` and as percentage for noise type
            ``relative_percent``.

    Raises:
        ValueError: If ``noise_type`` is neither ``absolute`` nor
            ``relative_percent``.
    """
    # Validate input
    if noise_type not in ("relative_percent", "absolute"):
        raise ValueError(
            f"Parameter 'noise_type' was {noise_type} but must be either "
            "'absolute' or 'relative_percent'."
        )

    for param in (p for p in parameters if p.is_numeric):
        # Add selected noise type
        if noise_type == "relative_percent":
            data[param.name] *= np.random.uniform(
                1.0 - noise_level / 100.0, 1.0 + noise_level / 100.0, len(data)
            )
        elif noise_type == "absolute":
            data[param.name] += np.random.uniform(-noise_level, noise_level, len(data))

        # Respect continuous intervals
        if not param.is_discrete:
            data[param.name].clip(param.bounds.lower, param.bounds.upper, inplace=True)


def df_drop_single_value_columns(
    df: pd.DataFrame, lst_exclude: list = None
) -> pd.DataFrame:
    """Drop dataframe columns with zero variance.

    Args:
        df: The dataframe to be cleaned.
        lst_exclude: List of column names that are excluded from this filter.

    Returns:
        The cleaned dataframe.
    """
    if lst_exclude is None:
        lst_exclude = []

    to_keep = []
    for col in df.columns:
        if (col in lst_exclude) or (df[col].nunique() > 1):
            to_keep.append(col)

    return df[to_keep]


def df_drop_string_columns(
    df: pd.DataFrame, ignore_list: Optional[List[str]] = None
) -> pd.DataFrame:
    """Drop dataframe columns with string values.

    Args:
        df: The dataframe to be cleaned.
        ignore_list: List of columns that should not be dropped, even if they include
            string values.

    Returns:
        The cleaned dataframe.
    """
    ignore_list = ignore_list or []
    no_string = ~df.applymap(lambda x: isinstance(x, str)).any()
    no_string = no_string[no_string].index
    to_keep = set(no_string).union(set(ignore_list))
    ordered_cols = [col for col in df if col in to_keep]
    return df[ordered_cols]


def df_uncorrelated_features(
    df: pd.DataFrame, exclude_list: Optional[List[str]] = None, threshold: float = 0.7
):
    """Return an uncorrelated set of features.

    Adapted from edbo (https://github.com/b-shields/edbo ,
    https://doi.org/10.1038/s41586-021-03213-y).

    Args:
        df: The dataframe to be cleaned
        exclude_list: If provided this defines the columns that should be ignored
        threshold: Threshold for column-column correlation above which columns should
            be dropped

    Returns:
        A new dataframe
    """
    # TODO: revise or replace with VRE method

    if exclude_list is None:
        data = df.copy()
    else:
        data = df.drop(columns=exclude_list)

    corr = data.corr().abs()
    to_keep = []
    for i in range(len(corr.iloc[:, 0])):
        above = corr.iloc[:i, i]
        if len(to_keep) > 0:
            above = above[to_keep]
        if len(above[above < threshold]) == len(above):
            to_keep.append(corr.columns.values[i])

    data = data[to_keep]

    if exclude_list is not None:
        data[exclude_list] = df.loc[:, exclude_list]

    return data


def fuzzy_row_match(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    parameters: List[Parameter],
    numerical_measurements_must_be_within_tolerance: bool,
) -> pd.Index:
    """Match row of the right dataframe to the rows of the left dataframe.

    This is useful for validity checks and to automatically match measurements to
    entries in the search space, e.g. to detect which ones have been measured.
    For categorical parameters, there needs to be an exact match with any of the
    allowed values. For numerical parameters, the user can decide via a flag
    whether values outside the tolerance should be accepted.

    Args:
        left_df: The data that serves as lookup reference.
        right_df: The data that should be checked for matching rows in the left
            dataframe.
        parameters: List of baybe parameter objects that are needed to identify
            potential tolerances.
        numerical_measurements_must_be_within_tolerance: If ``True``, numerical
            parameters are matched with the search space elements only if there is a
            match within the parameter tolerance. If ``False``, the closest match is
            considered, irrespective of the distance.

    Returns:
        The index of the matching rows in ``left_df``.

    Raises:
        ValueError: If some rows are present in the right but not in the left dataframe.
        ValueError: If the input data has invalid values.
    """
    # Assert that all parameters appear in the given dataframe
    if not all(col in right_df.columns for col in left_df.columns):
        raise ValueError(
            "For fuzzy row matching all rows of the right dataframe need to be present"
            " in the left dataframe."
        )

    inds_matched = []

    # Iterate over all input rows
    for ind, row in right_df.iterrows():
        # Check if the row represents a valid input
        valid = True
        for param in parameters:
            if param.is_numeric:
                if numerical_measurements_must_be_within_tolerance:
                    valid &= param.is_in_range(row[param.name])
            else:
                valid &= param.is_in_range(row[param.name])
            if not valid:
                raise ValueError(
                    f"Input data on row with the index {row.name} has invalid "
                    f"values in parameter '{param.name}'. "
                    f"For categorical parameters, values need to exactly match a "
                    f"valid choice defined in your config. "
                    f"For numerical parameters, a match is accepted only if "
                    f"the input value is within the specified tolerance/range. Set "
                    f"the flag 'numerical_measurements_must_be_within_tolerance' "
                    f"to 'False' to disable this behavior."
                )

        # Differentiate category-like and discrete numerical parameters
        cat_cols = [p.name for p in parameters if not p.is_numeric]
        num_cols = [p.name for p in parameters if (p.is_numeric and p.is_discrete)]

        # Discrete parameters must match exactly
        match = left_df[cat_cols].eq(row[cat_cols]).all(axis=1, skipna=False)

        # For numeric parameters, match the entry with the smallest deviation
        # TODO: allow alternative distance metrics
        for col in num_cols:
            abs_diff = (left_df[col] - row[col]).abs()
            match &= abs_diff == abs_diff.min()

        # We expect exactly one match. If that's not the case, print a warning.
        inds_found = left_df.index[match].to_list()
        if len(inds_found) == 0 and len(num_cols) > 0:
            _logger.warning(
                "Input row with index %s could not be matched to the search space. "
                "This could indicate that something went wrong.",
                ind,
            )
        elif len(inds_found) > 1:
            _logger.warning(
                "Input row with index %s has multiple matches with "
                "the search space. This could indicate that something went wrong. "
                "Matching only first occurrence.",
                ind,
            )
            inds_matched.append(inds_found[0])
        else:
            inds_matched.extend(inds_found)

    return pd.Index(inds_matched)

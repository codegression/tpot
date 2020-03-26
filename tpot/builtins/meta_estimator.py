# -*- coding: utf-8 -*-

"""This file is part of the TPOT library.

TPOT was primarily developed at the University of Pennsylvania by:
    - Randal S. Olson (rso@randalolson.com)
    - Weixuan Fu (weixuanf@upenn.edu)
    - Daniel Angell (dpa34@drexel.edu)
    - and many more generous open source contributors

TPOT is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as
published by the Free Software Foundation, either version 3 of
the License, or (at your option) any later version.

TPOT is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with TPOT. If not, see <http://www.gnu.org/licenses/>.

"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.utils import check_array
from sklearn.linear_model import LinearRegression, LogisticRegression

def check_if_any_float(snp_array):
    """Check if any float in a feature.

    Parameters
    ----------
    snp_array : np.ndarray
    1-D array for values in a feature

    Return
    ----------
    if_any_float: boolean
        True: This feature has at least one float number
    """
    if_any_float = False
    for a in snp_array:
        if int(a) != a: # a float was convert to int with different round value
            if_any_float = True
            break
    return


def X_adj_fit(X_train, C_train):
    """transform X_train by a list of confounding features.

    Parameters
    ----------
    X_train : pd.DataFrame
    C_train: pd.DataFrame for a confounding covariate.

    Return
    ----------
    X_train_adj: transformed/adjusted X_train
    col_est: estimators for each columns
    values: # types for each columns
    """


    col_est = [] # store estimator for each columns
    values = [] # store values for each columns
    if X_train.empty:
        return X_train, col_est, values
    else:
        X_train_adj = np.zeros(X_train.shape)
        for col in range(X_train.shape[1]):
            X_train_col = X_train.iloc[:, col].values # np.ndarray
            # test information cannot be used in fit() function
            # may be values should be provided as a parameter in __init__ above
            # here values was stored into self.values_list and can be used in predict
            # function below for test dataset
            # if there are float values in the X_train_col
            # then it is dosage else ternary
            if check_if_any_float(X_train_col):
                value = 'dosage'
            else:
                value = 'ternary'
            values.append(value)
            if values == 'dosage':
                regr = LinearRegression()
                regr.fit(C_train, X_train_col)
                est_pred = regr.predict(C_train)
                X_train_adj[:, col] = X_train_col - est_pred
                col_est.append(regr)
            else:
                clf = LogisticRegression(penalty='none',
                                        solver='lbfgs',
                                        multi_class='auto')
                clf.fit(C_train, X_train_col.astype(np.int32))
                clf_pred_proba = clf.predict_proba(C_train)

                X_train_col_adj = X_train_col
                # clf.classes_ should return an array of genotypes in this column
                # like array([0, 1, 2]) or array([0, 1])
                for gt_idx, gt in enumerate(clf.classes_):
                    gt = int(gt)
                    X_train_col_adj = X_train_col_adj - gt*clf_pred_proba[:, gt_idx]
                X_train_adj[:, col] = X_train_col_adj
                col_est.append(clf)
        return X_train_adj, col_est, values

def X_adj_predict(X_test, C_test, col_est, values):
    """transform X_test by a list of confounding features.

    Parameters
    ----------
    X_test : pd.DataFrame
    C_test: pd.DataFrame for a confounding covariate
    col_est: estimators for each columns
    values: # types for each columns

    Return
    ----------
    X_test_adj: transformed/adjusted X_train

    """
    if X_test.empty:
        return X_test
    else:
        X_test_adj = np.zeros(X_test.shape)
        for values, est, col in zip(values, col_est, range(X_test.shape[1])):
            X_test_col = X_test.iloc[:, col].values
            if values == 'dosage':
                est_pred = est.predict(C_test)
                X_test_adj[:, col] = X_test_col - est_pred
            else:
                clf_pred_proba = est.predict_proba(C_test)
                X_test_col_adj = X_test_col
                for gt_idx, gt in enumerate(est.classes_):
                    gt = int(gt)
                    X_test_col_adj = X_test_col_adj - gt*clf_pred_proba[:, gt_idx]
                X_test_adj[:, col] = X_test_col_adj
        return X_test_adj


class MetaRegressor(BaseEstimator, RegressorMixin):
    """Meta-transformer for adding predictions and/or class probabilities as synthetic feature(s).

    Parameters
    ----------
    estimator : object
        The base estimator from which the transformer is built.
    """

    def __init__(self, estimator, A=None, C=None, subset=None):
        """Create a StackingEstimator object.

        Parameters
        ----------
        estimator: object with fit, predict, and predict_proba methods.
            The estimator to generate synthetic features from.
        A: a list of columns for A, e.g ["N1", "N2"]
            columns of A correspond to a non-confounding covariate.
        C:  a list of columns for C, e.g ["N4", "N5"]
            columns of C correspond correspond to a confounding covariate.
        subset: None: all the features should be transformed by C
                list: a list of feature names should be transformed by C: e.g
                      ["N6", "N7"]
                tuples: the first element in a tuple should be a list of
                    features in C, the second element should be a list of feature
                    names should be transformed by feature in first element,
                    e.g. ((['N1'], ['N6', 'N7']), (['N2'], ['N8', 'N9']))

        """
        self.estimator = estimator
        self.A = A
        self.C = C
        self.subset = subset


    def fit(self, X, y=None, **fit_params):
        """Fit the StackingEstimator meta-transformer.

        Parameters
        ----------
        X: pd.DataFrame of shape (n_samples, n_features)
            The training input samples.
        y: array-like, shape (n_samples,)
            The target values (integers that correspond to classes in classification, real numbers in regression).
        fit_params:
            Other estimator-specific parameters.

        Returns
        -------
        self: object
            Returns a copy of the estimator
        """
        if self.A is None and self.C is None:
            raise(ValueError, "At least one of A_train and C_train must be specified")
        X_train = pd.DataFrame.copy(X)
        if self.A is not None:
            X_train.drop(self.A, axis=1, inplace=True)
        if self.C is not None:
            X_train.drop(self.C, axis=1, inplace=True)
        if self.C is None:
            X_train_adj = X_train
            C_train = None
        else:
            self.col_ests = []
            self.values_list = []
            C_train = X[self.C].values
            if self.subset is None:
                X_train_adj, col_est, values = X_adj_fit(X_train, C_train)
                self.col_ests.append(col_est)
                self.values_list.append(values)
            elif isinstance(self.subset, list):
                # overlap features
                comm_features = [a for a in self.subset if a in X_train.columns]
                X_train_subset = X_train[comm_features]
                X_subset_adj, col_est, values = \
                                            X_adj_fit(X_train_subset, C_train)
                # X that has no need to transform
                X_train_unsel = X_train.drop(comm_features, axis=1).values
                X_train_adj = np.hstack((X_subset_adj, X_train_unsel))
                self.col_ests.append(col_est)
                self.values_list.append(values)
            elif isinstance(self.subset, tuple):
                self.sel_subset = [] # collect all transformed features
                X_subset_adj = np.array([]) # make a empty array
                for subC, ssubset in self.subset:
                    comm_features = [a for a in ssubset if a in X_train.columns]
                    self.sel_subset += comm_features
                    tmp_C_train = X[subC].values
                    X_train_subset = X_train[comm_features]
                    tmp_X_subset_adj, col_est, values = \
                                            X_adj_fit(X_train_subset, tmp_C_train)
                    if X_subset_adj.size == 0:
                        X_subset_adj = tmp_X_subset_adj
                    else:
                        X_subset_adj = np.hstack((X_subset_adj, tmp_X_subset_adj))
                    self.col_ests.append(col_est)
                    self.values_list.append(values)
                X_train_unsel = X_train.drop(self.sel_subset, axis=1).values
                X_train_adj = np.hstack((X_subset_adj, X_train_unsel))

        if self.A is not None:
            A_train = X[self.A].values
        if self.C is None and self.A is not None:
            B_train = A_train
        elif self.A is None and self.C is not None:
            B_train = C_train
        else:
            B_train = np.hstack((A_train, C_train))
        self.B_est = LinearRegression()
        self.B_est.fit(B_train, y)
        pi_train = np.ravel(self.B_est.predict(B_train).reshape((-1, 1)))

        y_train_adj = y - pi_train

        self.estimator.fit(X_train_adj, y_train_adj, **fit_params)
        return self

    def predict(self, X):
        """Transform data by adding two synthetic feature(s).

        Parameters
        ----------
        X: pd.DataFrame, {n_samples, n_components}
            New data, where n_samples is the number of samples and n_components is the number of components.

        Returns
        -------
        y_pred: array-like, shape (n_samples, )
        """
        X_test = pd.DataFrame.copy(X)
        if self.A is not None:
            X_test.drop(self.A, axis=1, inplace=True)
        if self.C is not None:
            X_test.drop(self.C, axis=1, inplace=True)
        if self.C is None:
            X_test_adj = X_test
            C_test = None
        else:
            C_test = X[self.C].values
            if self.subset is None:

                X_test_adj = X_adj_predict(X_test,
                                            C_test,
                                            self.col_ests[0],
                                            self.values_list[0])
            elif isinstance(self.subset, list):
                comm_features = [a for a in self.subset if a in X_test.columns]
                X_test_subset = X_test[comm_features]
                # X that has no need to transform
                X_test_unsel = X_test.drop(self.subset, axis=1).values
                X_subset_adj =  X_adj_predict(X_test_subset,
                                            C_test,
                                            self.col_ests[0],
                                            self.values_list[0])
                X_test_adj = np.hstack((X_subset_adj, X_test_unsel))
            elif isinstance(self.subset, tuple):
                X_subset_adj = np.array([]) # make a empty array
                for sub, col_est, values in zip(self.subset,
                                                self.col_ests,
                                                self.values_list):
                    tmp_C_test = X[sub[0]].values
                    comm_features = [a for a in sub[1] if a in X_test.columns]
                    X_test_subset = X_test[comm_features]
                    tmp_X_subset_adj = X_adj_predict(X_test_subset,
                                                    tmp_C_test,
                                                    col_est,
                                                    values)
                    if X_subset_adj.size == 0:
                        X_subset_adj = tmp_X_subset_adj
                    else:
                        X_subset_adj = np.hstack((X_subset_adj, tmp_X_subset_adj))
                X_test_unsel = X_test.drop(self.sel_subset, axis=1).values
                X_test_adj = np.hstack((X_subset_adj, X_test_unsel))

        if self.A is not None:
            A_test = X[self.A].values
        if self.A is None and self.C is None:
            raise(ValueError, "At least one of A_train and C_train must be specified")
        elif self.C is None and self.A is not None:
            B_test = A_test
        elif self.A is None and self.C is not None:
            B_test = C_test
        else:
            B_test = np.hstack((A_test, C_test))
        # check line 400 for multi-class classification)
        pi_test = np.ravel(self.B_est.predict(B_test).reshape((-1, 1)))
        y_test_adj_pred = self.estimator.predict(X_test_adj)
        y_test_adj_pred_pi = y_test_adj_pred + pi_test
        y_pred = y_test_adj_pred_pi
        return y_pred


class MetaClassifier(BaseEstimator, ClassifierMixin):
    """Meta-transformer for adding predictions and/or class probabilities as synthetic feature(s).

    Parameters
    ----------
    estimator : object
        The base estimator from which the transformer is built.
    """

    def __init__(self, estimator, A=None, C=None, subset=None):
        """Create a StackingEstimator object.

        Parameters
        ----------
        estimator: object with fit, predict, and predict_proba methods.
            The estimator to generate synthetic features from.
        A: a list of columns for A, e.g ["N1", "N2"]
            columns of A correspond to a non-confounding covariate.
        C:  a list of columns for C, e.g ["N4", "N5"]
            columns of C correspond to a confounding covariate.
        subset: None: all the features should be transformed by C
                list: a list of feature names should be transformed by C: e.g
                      ["N6", "N7"]
                tuples: the first element in a tuple should be a list of
                    features in C, the second element should be a list of feature
                    names should be transformed by feature in first element,
                    e.g. ((['N1'], ['N6', 'N7']), (['N2'], ['N8', 'N9']))
        """
        self.estimator = estimator
        self.A = A
        self.C = C
        self.subset = subset

    def fit(self, X, y=None, **fit_params):
        """Fit the StackingEstimator meta-transformer.

        Parameters
        ----------
        X: pd.DataFrame of shape (n_samples, n_features)
            The training input samples.
        y: array-like, shape (n_samples,)
            The target values (integers that correspond to classes in classification, real numbers in regression).
        fit_params:
            Other estimator-specific parameters.

        Returns
        -------
        self: object
            Returns a copy of the estimator
        """
        if self.A is None and self.C is None:
            raise(ValueError, "At least one of A_train and C_train must be specified")
        X_train = pd.DataFrame.copy(X)
        if self.A is not None:
            X_train.drop(self.A, axis=1, inplace=True)
        if self.C is not None:
            X_train.drop(self.C, axis=1, inplace=True)
        if self.C is None:
            X_train_adj = X_train
            C_train = None
        else:
            self.col_ests = []
            self.values_list = []
            C_train = X[self.C].values
            if self.subset is None:
                X_train_adj, col_est, values = X_adj_fit(X_train, C_train)
                self.col_ests.append(col_est)
                self.values_list.append(values)
            elif isinstance(self.subset, list):
                # overlap features
                comm_features = [a for a in self.subset if a in X_train.columns]
                X_train_subset = X_train[comm_features]
                X_subset_adj, col_est, values = \
                                            X_adj_fit(X_train_subset, C_train)
                # X that has no need to transform
                X_train_unsel = X_train.drop(comm_features, axis=1).values
                X_train_adj = np.hstack((X_subset_adj, X_train_unsel))
                self.col_ests.append(col_est)
                self.values_list.append(values)
            elif isinstance(self.subset, tuple):
                self.sel_subset = [] # collect all transformed features
                X_subset_adj = np.array([]) # make a empty array
                for subC, ssubset in self.subset:
                    comm_features = [a for a in ssubset if a in X_train.columns]
                    self.sel_subset += comm_features
                    tmp_C_train = X[subC].values
                    X_train_subset = X_train[comm_features]
                    tmp_X_subset_adj, col_est, values = \
                                            X_adj_fit(X_train_subset, tmp_C_train)
                    if X_subset_adj.size == 0:
                        X_subset_adj = tmp_X_subset_adj
                    else:
                        X_subset_adj = np.hstack((X_subset_adj, tmp_X_subset_adj))
                    self.col_ests.append(col_est)
                    self.values_list.append(values)
                X_train_unsel = X_train.drop(self.sel_subset, axis=1).values
                X_train_adj = np.hstack((X_subset_adj, X_train_unsel))

        if self.A is not None:
            A_train = X[self.A].values


        if self.C is None and self.A is not None:
            B_train = A_train
        elif self.A is None and self.C is not None:
            B_train = C_train
        else:
            B_train = np.hstack((A_train, C_train))

        # EM
        self.B_est = LogisticRegression(penalty='none',
                                        solver='lbfgs',
                                        multi_class='auto')
        self.B_est.fit(B_train, y)
        B_est_pred_proba = self.B_est.predict_proba(B_train)
        pi_train = np.zeros(y.shape)
        for gt_idx, gt in enumerate(self.B_est.classes_):
            gt = int(gt)
            pi_train = pi_train + gt*B_est_pred_proba[:, gt_idx]
        y_train_adj = y - pi_train

        self.estimator.fit(X_train_adj, y_train_adj, **fit_params)
        return self

    def predict(self, X):
        """Transform data by adding two synthetic feature(s).

        Parameters
        ----------
        X: pd.DataFrame, {n_samples, n_components}
            New data, where n_samples is the number of samples and n_components is the number of components.

        Returns
        -------
        y_pred: array-like, shape (n_samples, )
        """
        X_test = pd.DataFrame.copy(X)
        if self.A is not None:
            X_test.drop(self.A, axis=1, inplace=True)
        if self.C is not None:
            X_test.drop(self.C, axis=1, inplace=True)
        if self.C is None:
            X_test_adj = X_test
            C_test = None
        else:
            C_test = X[self.C].values
            if self.subset is None:

                X_test_adj = X_adj_predict(X_test,
                                            C_test,
                                            self.col_ests[0],
                                            self.values_list[0])
            elif isinstance(self.subset, list):
                comm_features = [a for a in self.subset if a in X_test.columns]
                X_test_subset = X_test[comm_features]
                # X that has no need to transform
                X_test_unsel = X_test.drop(self.subset, axis=1).values
                X_subset_adj =  X_adj_predict(X_test_subset,
                                            C_test,
                                            self.col_ests[0],
                                            self.values_list[0])
                X_test_adj = np.hstack((X_subset_adj, X_test_unsel))
            elif isinstance(self.subset, tuple):
                X_subset_adj = np.array([]) # make a empty array
                for sub, col_est, values in zip(self.subset,
                                                self.col_ests,
                                                self.values_list):
                    tmp_C_test = X[sub[0]].values
                    comm_features = [a for a in sub[1] if a in X_test.columns]
                    X_test_subset = X_test[comm_features]
                    tmp_X_subset_adj = X_adj_predict(X_test_subset,
                                                    tmp_C_test,
                                                    col_est,
                                                    values)
                    if X_subset_adj.size == 0:
                        X_subset_adj = tmp_X_subset_adj
                    else:
                        X_subset_adj = np.hstack((X_subset_adj, tmp_X_subset_adj))
                X_test_unsel = X_test.drop(self.sel_subset, axis=1).values
                X_test_adj = np.hstack((X_subset_adj, X_test_unsel))

        if self.A is not None:
            A_test = X[self.A].values
        if self.A is None and self.C is None:
            raise(ValueError, "At least one of A_train and C_train must be specified")
        elif self.C is None and self.A is not None:
            B_test = A_test
        elif self.A is None and self.C is not None:
            B_test = C_test
        else:
            B_test = np.hstack((A_test, C_test))

        pi_test = np.ravel(self.B_est.predict_proba(B_test)[:, 1])

        y_test_adj_pred = self.estimator.predict(X_test_adj)
        B_est_pred_proba = self.B_est.predict_proba(B_test)
        pi_test = np.zeros(y_test_adj_pred.shape)
        for gt_idx, gt in enumerate(self.B_est.classes_):
            gt = int(gt)
            pi_test = pi_test + gt*B_est_pred_proba[:, gt_idx]
        y_test_adj_pred_pi = y_test_adj_pred + pi_test

        # define min. max value in B_est.classes_
        min_c, max_c = min(self.B_est.classes_), max(self.B_est.classes_)
        y_pred = np.rint(y_test_adj_pred_pi)
        y_pred[np.where(y_test_adj_pred_pi<min_c)] = min_c
        y_pred[np.where(y_test_adj_pred_pi>max_c)] = max_c
        return y_pred

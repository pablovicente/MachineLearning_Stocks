"""
Stacking.py

Original author: Paul Duan <email@paulduan.com>
Modified by: Pablo Vicente 
"""

import scipy as sp
import numpy as np
import multiprocessing
import itertools

from functools import partial
from operator import itemgetter

from sklearn.metrics import roc_curve, auc, accuracy_score
from sklearn.grid_search import GridSearchCV
from sklearn import cross_validation, linear_model

from utils import toString
from classifier_utils import compute_auc, compute_subset_auc, compute_score, compute_subset_score, compute_f1_score


class Stacking(object):
    
    def __init__(self, models, generalizer=None, model_selection=True,
                 stack=False, fwls=False, log = None):        
        self.models = models
        self.model_selection = model_selection
        self.stack = stack
        self.fwls = fwls
        self.generalizer = linear_model.RidgeCV(alphas=np.linspace(0, 200), cv=100)    
        self.log = log

    def fit(self, y, train):

        y_train = y
        X_train = train

        for model, hyperfeatures in self.models:
            if self.log != None:
                        print >> self.log, "Fitting [%s]" % (toString(model, hyperfeatures))
            else:
                print "Fitting [%s]"  % (toString(model, hyperfeatures))

            model_preds = model.fit(X_train, y_train)
            

    def predict(self, y, train, predict, y_test, show_steps=True):
        
        stage0_train = []
        stage0_predict = [] 

        models_score = []
        means_score = []
        stacks_score = []

        models_f1 = []
        means_f1 = []
        stacks_f1 = []

        y_train = y
        X_train = train
        X_predict = predict

        for model, hyperfeatures in self.models:

            model_preds = self._get_model_preds(model, X_predict)
            model_score = self._get_model_score(model, X_predict, y_test)             
            stage0_predict.append(model_preds)
        
            # if stacking, compute cross-validated predictions on the train set
            if self.stack:
                model_cv_preds = self._get_model_cv_preds(model, X_train, y_train)
                stage0_train.append(model_cv_preds)

            # verbose mode: compute metrics after every model computation
            if show_steps:                
                    mean_preds, stack_preds, fwls_preds = self._combine_preds(
                        np.array(stage0_train).T, np.array(stage0_predict).T,
                        y_train, train, predict,
                        stack=self.stack, fwls=self.fwls)

                    #model_auc = compute_auc(y_test, stage0_predict[-1])
                    #mean_auc = compute_auc(y_test, mean_preds)
                    #stack_auc = compute_auc(y_test, stack_preds) \
                    #    if self.stack else 0
                    #fwls_auc = compute_auc(y_test, fwls_preds) \
                    #    if self.fwls else 0
                    #
                    #if self.log != None:
                    #    print >> self.log, "> AUC: %.4f (%.4f, %.4f, %.4f) [%s]" % (model_auc, mean_auc, stack_auc, fwls_auc, toString(model, hyperfeatures))
                    #else:
                    #    print "> AUC: %.4f (%.4f, %.4f, %.4f) [%s]" % (model_auc, mean_auc, stack_auc, fwls_auc, toString(model, hyperfeatures))

                    model_preds_bin, mean_preds_bin, stack_preds_bin = self._binary_preds(model_preds, mean_preds, stack_preds)
                    model_score = compute_score(y_test, model_preds_bin)
                    mean_score = compute_score(y_test, mean_preds_bin)
                    stack_score = compute_score(y_test, stack_preds_bin) \
                        if self.stack else 0
                    models_score.append(model_score)
                    means_score.append(mean_score)
                    stacks_score.append(stack_score) \
                        if self.stack else 0            

                    if self.log != None:
                        print >> self.log, "> Score: %.4f (%.4f, %.4f) [%s]" % (model_score, mean_score, stack_score, toString(model, hyperfeatures))
                    else:
                        print "> Score: %.4f (%.4f, %.4f) [%s]" % (model_score, mean_score, stack_score, toString(model, hyperfeatures))
                
                    model_f1 = compute_f1_score(y_test, model_preds_bin)
                    mean_f1 = compute_f1_score(y_test, mean_preds_bin)
                    stack_f1 = compute_f1_score(y_test, stack_preds_bin) \
                        if self.stack else 0
                    models_f1.append(model_f1)
                    means_f1.append(mean_f1)
                    stacks_f1.append(stack_f1) \
                        if self.stack else 0

                    if self.log != None:
                        print >> self.log, "> F1: %.4f (%.4f, %.4f) [%s]" % (model_f1, mean_f1, stack_f1, toString(model, hyperfeatures))
                    else:
                        print "> F1: %.4f (%.4f, %.4f) [%s]" % (model_f1, mean_f1, stack_f1, toString(model, hyperfeatures))            

        if self.model_selection and predict is not None:

            #best_subset = self._find_best_auc_subset(y_test, stage0_predict)  
            best_subset = self._find_best_score_subset(y_test, stage0_predict)  

            stage0_train = [pred for i, pred in enumerate(stage0_train)
                            if i in best_subset]

            stage0_predict = [pred for i, pred in enumerate(stage0_predict)
                              if i in best_subset]

        mean_preds, stack_preds, fwls_preds = self._combine_preds(
            np.array(stage0_train).T, np.array(stage0_predict).T,
            y_train, stack=self.stack, fwls=self.fwls)

        if self.stack:
            selected_preds = stack_preds if not self.fwls else fwls_preds
        else:
            selected_preds = mean_preds

        return selected_preds, models_score, models_f1

    def _get_model_preds(self, model, X_predict):
        """        
        
        """        
        model_preds = model.predict_proba(X_predict)[:, 1]                    
        return model_preds

    def _get_model_score(self, model, X_predict, y_test):
        """
        """
        score = model.score(X_predict, y_test)
        return score

    def _get_model_cv_preds(self, model, X_train, y_train):
        """
        Return cross-validation predictions on the training set.       
        
        This is used if stacking is enabled (ie. a second model is used to
        combine the stage 0 predictions).
        """
        
        kfold = cross_validation.StratifiedKFold(y_train, 4)
        stack_preds = []
        indexes_cv = []
        for stage0, stack in kfold:
            model.fit(X_train[stage0], y_train[stage0])
            stack_preds.extend(list(model.predict_proba(X_train[stack])[:, 1]))
            indexes_cv.extend(list(stack))
        stack_preds = np.array(stack_preds)[sp.argsort(indexes_cv)]

        return stack_preds        

    def _combine_preds(self, X_train, X_cv, y, train=None, predict=None,
                       stack=False, fwls=False):
        """
        Combine preds, returning in order:
            - mean_preds: the simple average of all model predictions
            - stack_preds: the predictions of the stage 1 generalizer
            - fwls_preds: same as stack_preds, but optionally using more
                complex blending schemes (meta-features, different
                generalizers, etc.)
        """
        mean_preds = np.mean(X_cv, axis=1)
        stack_preds = None
        fwls_preds = None

        if stack:
            self.generalizer.fit(X_train, y)
            stack_preds = self.generalizer.predict(X_cv)

        #if self.fwls:
        #    meta, meta_cv = get_dataset('metafeatures', train, predict)
        #    fwls_train = np.hstack((X_train, meta))
        #    fwls_cv = np.hstack((X_cv, meta))
        #    self.generalizer.fit(fwls_train)
        #    fwls_preds = self.generalizer.predict(fwls_cv)

        return mean_preds, stack_preds, fwls_preds        

    def _find_best_auc_subset(self, y, predictions_list):
        """
        Finds the combination of models that produce the best AUC.
        """

        best_subset_indices = range(len(predictions_list))
        pool = multiprocessing.Pool(processes=4)
        partial_compute_subset_auc = partial(compute_subset_auc,
                                             pred_set=predictions_list, y=y)

        best_auc = 0
        best_n = 0
        best_indices = []

        if len(predictions_list) == 1:
            return [1]

        for n in range(int(len(predictions_list)/2), len(predictions_list)):
            cb = itertools.combinations(range(len(predictions_list)), n)
            combination_results = pool.map(partial_compute_subset_auc, cb)
            best_subset_auc, best_subset_indices = max(
                combination_results, key=itemgetter(0))
            if self.log != None:
                print >> self.log, "- best subset auc (%d models): %.4f > %s" % (
                n, best_subset_auc, list(best_subset_indices))
            else:
                print "- best subset auc (%d models): %.4f > %s" % (
                n, best_subset_auc, list(best_subset_indices))
            if best_subset_auc > best_auc:
                best_auc = best_subset_auc
                best_n = n
                best_indices = list(best_subset_indices)
        pool.terminate()
        
        if self.log != None:                    
            print >> self.log, "best auc: %.4f" % (best_auc)
            print >> self.log, "best n: %d" % (best_n)
            print >> self.log, "best indices: %s" % (best_indices)
        else:
            print "best auc: %.4f" % (best_auc)
            print "best n: %d" % (best_n)
            print "best indices: %s" % (best_indices)

        for i, (model, feature_set) in enumerate(self.models):
            if i in best_subset_indices:
                if self.log != None:                    
                    print >> self.log, "> model: %s (%s)" % (model.__class__.__name__, feature_set)        
                else:
                    print "> model: %s (%s)" % (model.__class__.__name__, feature_set)        

        return best_subset_indices
    
    def _find_best_score_subset(self, y, predictions_list):
        """
        Finds the combination of models that produce the best accuracy.
        """
        
        best_subset_indices = range(len(predictions_list))
        pool = multiprocessing.Pool(processes=4)
        partial_compute_subset_score = partial(compute_subset_score,
                                             pred_set=predictions_list, y=y)

        best_auc = 0
        best_n = 0
        best_indices = []

        if len(predictions_list) == 1:
            return [1]    

        for n in range(int(len(predictions_list)/2), len(predictions_list)):
            cb = itertools.combinations(range(len(predictions_list)), n)
            combination_results = pool.map(partial_compute_subset_score, cb)
            best_subset_auc, best_subset_indices = max(
                combination_results, key=itemgetter(0))
            if self.log != None:
                print >> self.log, "- best subset score (%d models): %.4f > %s" % (
                n, best_subset_auc, list(best_subset_indices))
            else:
                print "- best subset score (%d models): %.4f > %s" % (
                n, best_subset_auc, list(best_subset_indices))
            if best_subset_auc > best_auc:
                best_auc = best_subset_auc
                best_n = n
                best_indices = list(best_subset_indices)
        pool.terminate()

        if self.log != None:                    
            print >> self.log, "best score: %.4f" % (best_auc)
            print >> self.log, "best n: %d" % (best_n)
            print >> self.log, "best indices: %s" % (best_indices)
        else:
            print "best score: %.4f" % (best_auc)
            print "best n: %d" % (best_n)
            print "best indices: %s" % (best_indices)

        for i, (model, feature_set) in enumerate(self.models):
            if i in best_subset_indices:
                if self.log != None:                    
                    print >> self.log, "> model: %s (%s)" % (model.__class__.__name__, feature_set)        
                else:
                    print "> model: %s (%s)" % (model.__class__.__name__, feature_set)        
     

        return best_subset_indices

    def _binary_preds(self, model_preds, mean_preds, stack_preds):
        """
        """
        stack_preds_bin = []
        model_preds_bin = np.round_(model_preds, decimals=0)
        mean_preds_bin = np.round_(mean_preds, decimals=0)
        stack_preds_bin = np.round_(stack_preds, decimals=0) \
                        if self.stack else 0
                
        return model_preds_bin, mean_preds_bin, stack_preds_bin
        
# Iron Rules Documentation (Data Modeling Validation)

This document details the fundamental rules that guarantee the viability, precision, and robustness of our data models (particularly star schemas). Each rule acts as a mathematical and structural safety net.

## Level 1 & 4 Rules (Structure): Topology and Referential Integrity

The Goal: Ensure that the skeleton of our database is solid, connected end-to-end, and free of geometric dead-ends.

Pedagogical Explanation:
Imagine your data model as a road network or a family tree.

    Referential Integrity & Orphan Hunting: Every child must have a parent. If a sales row (Fact) points to a customer_id that does not exist in the Customer table (Dimension), this sale is an "orphan." It will float in limbo during analyses.

    Topology (Cycle Detection): If table A points to B, which points to C, which points back to A, we have created an infinite roundabout. In a database, a cycle causes infinite loops during queries (recursive queries that never terminate) and makes clean data aggregation impossible to resolve.

    What the test does: It traverses the relationship graph (adjacency matrices) to ensure that every foreign key corresponds to an existing primary key (0 orphans) and that there is no path allowing it to return to its starting point (Directed Acyclic Graph - DAG).

## Level 1 Rules (Separation): Semantic Homogeneity

The Goal: Maintain a strict and airtight separation between what we measure (Facts) and the context of the measurement (Dimensions).

Pedagogical Explanation:
Never mix the thermometer with the temperature.
A Dimension table contains descriptive attributes (text, categories, dates: Who, When, Where). A Fact table contains numerical metrics (amounts, quantities: How much). If a dimension starts storing sales amounts, or if a fact table stores a customer's full name and address, the model collapses and calculations become redundant.

Mathematical Proof:
Let F be the set of columns in a fact table and D be the set of columns in a dimension table.
The rule requires that the intersection of their semantic spaces (with the exception of the join keys K) is strictly empty:
(F∖K)∩(D∖K)=∅

    What the test does: It profiles the columns and proves that tables labeled as "Dimensions" have low variance and categorical types, while "Facts" are dominated by continuous, additive, and high-cardinality variables.

## Level 2 Rules (Precision): Deterministic Granularity

The Goal: Ensure that every row in a table is unique and perfectly identified by its primary key (whether simple or composite).

Pedagogical Explanation:
A postal address must point to one and only one house. If the address "10 Peace Street" refers to two different buildings, the mail carrier will never know where to deliver the package.
In data modeling, granularity is the finest level of detail. If we say the grain of a sales table is defined by the composite key (Date, Product, Store), then it is mathematically impossible to have two rows sharing exactly that same combination.

    What the test does: It verifies that the total row count of a table is strictly equal to the count of distinct values of its key (or combination of keys). If Count(Rows)=Count(Distinct(PK)), the granularity is not deterministic and will generate vicious duplicates during joins (Fan-out).

## Level 3 Rules (Aggregation): Aggregation Stability

The Goal: Validate the law of data conservation. The total of a measure must never change, regardless of how you slice or group it.

Pedagogical Explanation:
This is the pizza principle. Whether you cut a pizza into 4 large slices or 8 small slices, in the end, you still have exactly one and the same pizza.
If your total annual revenue is $100,000, and you decide to display this revenue grouped by month, the sum of the 12 months must equal exactly $100,000. If the amount inflates, it means your model has multiplied rows (often due to a bad many-to-many join). If it decreases, data was lost along the way (often a strict inner join on incomplete dimensions).

Mathematical Test:
Let M be a quantitative measure. The delta (Δ) between the sum at the finest grain and the sum after a GROUP BY on any dimension must be strictly zero:
Δ=Fine Grain∑​M−Aggregated Grain∑​M=0

    What the test does: It calculates the raw total of a measure in the fact table. Then, it simulates joins with the dimensions, groups the data, recalculates the total, and compares them. If Δ=0, the rule is broken, and the model candidate is invalidated.
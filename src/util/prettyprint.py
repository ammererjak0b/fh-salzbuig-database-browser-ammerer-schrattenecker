import datetime


# method for printing query results in a nice format
def print_results(results, cursor):
    if not results:
        print("No results found.")
        return

    # replace None (NULL) values with "NULL" for printing
    rows = [("NULL" if value is None else value for value in row) for row in results]
    # convert datetime objects to strings
    rows = [(value.strftime('%Y/%m/%d')
             if isinstance(value, datetime.datetime) else value for value in row) for row in rows]
    # convert generator to list
    rows = [(list(row)) for row in rows]

    # get column names and calculate max length of each column description contains a list of tuples (column name,
    # type, width, precision, scale, nullability) describing the columns
    columns = [desc[0] for desc in cursor.description]

    # calculate max length of each column value
    max_lengths = [max(len(str(row[i])) for row in rows) for i in range(len(cursor.description))]
    # take max of column name length and column value length
    max_lengths = [max_lengths[i] if max_lengths[i] > len(columns[i]) else len(columns[i]) for i in range(len(columns))]

    # format string for printing
    format_str = " | ".join("{:<" + str(max_lengths[i]) + "}" for i in range(len(max_lengths)))

    # print column names
    print(format_str.format(*columns))
    # print separator
    print("-" * (sum(max_lengths) + (3 * (len(max_lengths) - 1))))

    # print formatted results
    for row in rows:
        print(format_str.format(*row))

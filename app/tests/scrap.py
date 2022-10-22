class BaseModel(Model):
    @classmethod
    def insert_bulk(cls, rows, fields=[], db_step=250):
        """
        Insert many rows to the database in batches.

        Args:
            rows (list): list of rows to insert
            fields (list): list of fields to preserve on conflict

        Returns:
            int count: updated row count
        """
        count = 0
        for idx in range(0, len(rows), db_step):
            batch = rows[idx:idx + db_step]
            try:
                with db.atomic():
                    query = (cls
                             .insert_many(batch)
                             .on_conflict(preserve=fields))
                    if query.execute():
                        count += len(batch)
            except (IntegrityError, OperationalError):
                log.exception('Failed to insert %s batch.', cls.__name__)

        return count

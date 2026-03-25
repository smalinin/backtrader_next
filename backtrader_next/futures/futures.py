#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import datetime
import backtrader_next as bt
from backtrader_next import feed

__all__ = ['Futures', 'FuturesList']


class Futures():
    dt_start = None
    dt_end = None
    end = None
    name = None
    _data = None

    def __init__(self, name: str, start: datetime.datetime, end: datetime.datetime, fut_data: feed.DataBase):
        self.dt_start = start
        self.dt_end = end
        self.end = end.date()
        self.name = name
        self._data = fut_data

class FuturesList():
    _futures: list[Futures] = []
    _pos: int = -1
    _switch_time: datetime.time = None
    _names: list[str] = []
    _cur_fut: Futures = None
    _next_fut: Futures = None
    _next_dt: datetime.datetime = None

    def __init__(self, switch_time: datetime.time = datetime.time(10, 0, 0)):
        self._switch_time = switch_time
        self._futures = []
        self._names = []
        self._pos = -1
        self._cur_fut = None
        self._next_fut = None
        self._next_dt = None

    @property
    def names(self) -> list[str]:
        return self._names

    @property
    def switch_time(self) -> datetime.time:
        return self._switch_time

    @property
    def cur_fut(self) -> Futures:
        return self._cur_fut

    @property
    def futures(self) -> list[Futures]:
        return self._futures

    def add(self, name: str, start: datetime.datetime, end: datetime.datetime, fut: feed.DataBase):
        self._futures.append(Futures(name, start, end, fut))
        self._names.append(name)

    def start(self) -> bool:
        self._pos = -1
        if not self._futures:
            return False
        first = True
        for f in self._futures:
            f._data.is_on = False if not first else True
            f._data.is_end = False  # reset between optimization runs
            first = False
        return self.switch_futures()

    def is_switch_datetime(self, cur_dt: datetime.datetime) -> bool:
        """
        Determines whether the given cur_dt datetime meets the conditions to
        switch futures, based on the current future's end date and the
        configured switch time. Returns True if a switch should occur, otherwise
        False.
        """
        if self._next_dt is None:
            return False
        cur_fut = self._cur_fut
        if cur_dt.date() >= cur_fut.end and cur_dt.time() >= self._switch_time:
            return True
        return False

    def try_switch(self, cur_dt: datetime.datetime, strat: bt.Strategy = None) -> bool:
        """
        Checks if it's time to switch futures based on the current datetime and the configured switch time.
        If it's time to switch, it performs the switch and returns True. Otherwise, it returns False.

        Args:
            cur_dt (datetime.datetime): The current datetime to check against the switch conditions.
            strat (bt.Strategy, optional): The strategy instance to use for switching positions. Defaults to None.

        Returns:
            bool: True if a switch occurred, False otherwise.
        """
        if self.is_switch_datetime(cur_dt):
            return self.switch_futures(strat)
        return False


    def switch_futures(self, strat: bt.Strategy = None) -> bool:
        """
        Switch to next future, optionally closing current position on strat if provided 
        and opening position on next future with same size and direction if there is an open position on current future.

        Args:
            strat (bt.Strategy, optional): The strategy instance to use for switching positions. Defaults to None.

        Returns:
            bool: True if switch was successful, False if there are no more futures to switch to.
        """
        if strat is not None:  # check if need to switch position
            pos_sz = 0
            if self._next_fut is not None:
                if not self._next_fut._data.is_on:
                    raise ValueError(f"Next future {self._next_fut.name} is not active for switching, Check your date feed")
                cur_dt = self._cur_fut._data.datetime.datetime(0)
                next_dt = self._next_fut._data.datetime.datetime(0)
                if cur_dt != next_dt:
                    raise ValueError(f"Current future {self._cur_fut.name} and next future {self._next_fut.name} are not aligned on datetime for switching: {cur_dt} vs {next_dt}")

            if self._cur_fut is not None:
                cur_data = strat.getdatabyname(self._cur_fut.name)
                pos_sz = strat.getposition(data=cur_data).size
                if pos_sz != 0:
                    strat.close(data=cur_data, size=pos_sz)  # Close current position
                cur_data.is_end = True
            if self._next_fut is not None:  # Open position on next future
                next_data = strat.getdatabyname(self._next_fut.name)
                if pos_sz > 0:
                    strat.buy(data=next_data)
                elif pos_sz < 0:
                    strat.sell(data=next_data)

        self._pos += 1
        if self._pos >= len(self._futures):
            self._cur_fut = None
            self._next_fut = None
            self._pos = -1
            return False
        self._cur_fut = self._futures[self._pos]
        self._cur_fut._data.is_on = True
        if self._pos + 1 < len(self._futures):
            self._next_fut = self._futures[self._pos + 1]
            self._next_dt = self._next_fut.dt_start
        else:
            self._next_fut = None
            self._next_dt = None
        return True


    def check_date(self, dt: datetime.datetime) -> None:
        """
        Checks if the given datetime meets the conditions to switch to the next future. If the conditions are met, it activates the next future's data feed.

        Args:
            dt (datetime.datetime): The current datetime to check against the switch conditions.

        Returns:
            bool: True if the next future's data feed was activated, False otherwise.
        """
        if self._next_dt is None:
            return
        if not self._next_fut._data.is_on and dt >= self._next_dt:
            self._next_fut._data.is_on = True



#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Aurora Indicator - Optimized indicator base class for Aurora engine
#
###############################################################################
"""
AuroraIndicator - базовый класс индикаторов для Aurora.

Особенности:
- Совместимость с API стандартного Indicator
- Оптимизированный метод once() для работы с Aurora Lines
- Поддержка numpy векторизованных операций
- Упрощенная логика без поддержки разных timeframes

Основное отличие от стандартного Indicator:
- once() работает напрямую с numpy массивами Aurora Lines
- Не требует advance() для каждого бара
- Оптимизирован под runonce режим
"""

import numpy as np
from backtrader_next.lineiterator import LineIterator, IndicatorBase
from backtrader_next.utils.py3 import with_metaclass


class MetaAuroraIndicator(IndicatorBase.__class__):
    """
    Метакласс для Aurora индикаторов.
    
    Упрощенная версия MetaIndicator без кеширования и с фокусом
    на runonce режим.
    """
    
    _refname = '_indcol'
    _indcol = dict()
    
    def __init__(cls, name, bases, dct):
        """
        Регистрация индикатора и проверка методов.
        """
        super(MetaAuroraIndicator, cls).__init__(name, bases, dct)
        
        # Регистрация индикатора по имени
        if not cls.aliased and name != 'AuroraIndicator' and not name.startswith('_'):
            refattr = getattr(cls, cls._refname)
            refattr[name] = cls
        
        # Aurora работает только в режиме runonce
        # Если once() не переопределен, используем once_via_next
        next_over = cls.next != IndicatorBase.next
        once_over = cls.once != IndicatorBase.once
        
        if next_over and not once_over:
            cls.once = cls.once_via_next
            cls.preonce = cls.preonce_via_prenext
            cls.oncestart = cls.oncestart_via_nextstart


class AuroraIndicator(with_metaclass(MetaAuroraIndicator, IndicatorBase)):
    """
    Базовый класс индикаторов для Aurora.
    
    Наследуется от IndicatorBase для совместимости с backtrader API,
    но оптимизирован для работы с Aurora архитектурой.
    
    Ключевые методы:
    - once(start, end): Векторизованный расчет индикатора на диапазоне баров
    - next(): Расчет индикатора для текущего бара (fallback)
    
    Пример использования:
        class MySMA(AuroraIndicator):
            lines = ('sma',)
            params = (('period', 20),)
            
            def __init__(self):
                self.addminperiod(self.p.period)
            
            def once(self, start, end):
                # Векторизованный расчет через numpy
                src = self.data.close.array
                dst = self.lines.sma.array
                
                period = self.p.period
                for i in range(start, end):
                    dst[i] = np.mean(src[i-period+1:i+1])
    """
    
    _ltype = LineIterator.IndType
    csv = False
    
    def __init__(self):
        """
        Инициализация индикатора.
        
        Вызывается автоматически после создания объекта.
        Используется для настройки параметров и зависимостей.
        """
        super(AuroraIndicator, self).__init__()
    
    def _once(self):
        """
        Обертка для вызова once() - переопределяет стандартное поведение.
        
        В стандартном Indicator _once() работает с LineBuffer.once(),
        но для Aurora нам нужно вызывать наш кастомный once(start, end).
        """
        # DEBUG
        print(f"DEBUG: AuroraIndicator._once() called for {self.__class__.__name__}")
        
        # Получаем размер данных
        data_len = len(self._clock)
        if data_len <= 0:
            return
        
        # Сначала вызываем _once() для зависимых индикаторов
        for indicator in self._ind_iterator:
            indicator._once()
        
        # Устанавливаем размер наших линий
        self.lines.home()
        self.lines.extend(size=data_len)
        
        # Вызываем our once() для расчета
        self.preonce(0, self._minperiod - 1)
        self.oncestart(self._minperiod - 1, self._minperiod)
        self.once(self._minperiod, data_len)
        
        # Сбрасываем индекс
        self.home()
    
    def advance(self, size=1):
        """
        Продвижение индекса индикатора.
        
        Для Aurora индикаторов это упрощено, так как все lines
        используют единый индекс.
        
        Args:
            size (int): Количество баров для продвижения
        """
        # Проверка синхронизации с clock
        if len(self) < len(self._clock):
            self.lines.advance(size=size)
    
    def once(self, start, end):
        """
        Векторизованный расчет индикатора на диапазоне баров.
        
        Это основной метод для runonce режима. Должен быть переопределен
        в наследниках для реализации логики индикатора.
        
        Args:
            start (int): Начальный индекс (включительно)
            end (int): Конечный индекс (не включительно)
        
        Пример:
            def once(self, start, end):
                src = self.data.close.array
                dst = self.lines.myline.array
                
                for i in range(start, end):
                    dst[i] = src[i] * 2  # Удвоение цены
        
        Note:
            Для доступа к данным используйте .array вместо [i]:
            - src = self.data.close.array  # numpy array
            - dst[i] = src[i]  # прямой доступ к массиву
        """
        pass  # Переопределяется в наследниках
    
    def next(self):
        """
        Расчет индикатора для текущего бара.
        
        Fallback метод, вызывается только если once() не переопределен.
        Для Aurora рекомендуется переопределять once() вместо next().
        
        Пример:
            def next(self):
                self.lines.myline[0] = self.data.close[0] * 2
        """
        pass  # Переопределяется в наследниках
    
    def prenext(self):
        """
        Вызывается до достижения minperiod.
        
        По умолчанию не делает ничего. Может быть переопределен
        для специальной обработки "разогрева" индикатора.
        """
        pass
    
    def nextstart(self):
        """
        Вызывается один раз при достижении minperiod.
        
        По умолчанию вызывает next(). Может быть переопределен
        для специальной инициализации.
        """
        self.next()
    
    # Методы для fallback режима (если once не переопределен)
    
    def once_via_next(self, start, end):
        """
        Эмуляция once() через вызовы next().
        
        Используется автоматически, если once() не переопределен,
        но next() переопределен.
        
        Внимание: Медленнее чем нативный once()!
        """
        for i in range(start, end):
            # Продвинуть данные
            for data in self.datas:
                data.advance()
            
            # Продвинуть зависимые индикаторы
            for indicator in self._ind_iterator:
                indicator.advance()
            
            # Продвинуть себя и вызвать next()
            self.advance()
            self.next()
    
    def preonce_via_prenext(self, start, end):
        """
        Эмуляция preonce() через вызовы prenext().
        """
        for i in range(start, end):
            for data in self.datas:
                data.advance()
            
            for indicator in self._ind_iterator:
                indicator.advance()
            
            self.advance()
            self.prenext()
    
    def oncestart_via_nextstart(self, start, end):
        """
        Эмуляция oncestart() через вызов nextstart().
        """
        for i in range(start, end):
            for data in self.datas:
                data.advance()
            
            for indicator in self._ind_iterator:
                indicator.advance()
            
            self.advance()
            self.nextstart()
    
    # Утилиты для работы с numpy
    
    def get_array(self, line, length=None):
        """
        Получить numpy array из line.
        
        Args:
            line: Line object (например, self.data.close)
            length (int, optional): Длина массива. Если None, вся доступная длина.
        
        Returns:
            np.ndarray: Numpy массив с данными
        
        Example:
            close_array = self.get_array(self.data.close)
            sma_array = self.get_array(self.lines.sma)
        """
        if hasattr(line, 'array'):
            arr = line.array
        elif hasattr(line, 'get'):
            # Fallback для стандартных LineBuffer
            arr = np.array([line.get(ago=i) for i in range(len(line))])
        else:
            raise TypeError(f"Cannot extract array from {type(line)}")
        
        if length is not None:
            return arr[:length]
        return arr
    
    def set_array(self, line, array, start=0):
        """
        Установить значения из numpy array в line.
        
        Args:
            line: Line object для записи
            array (np.ndarray): Массив значений
            start (int): Начальный индекс для записи
        
        Example:
            result = np.mean(close_array)
            self.set_array(self.lines.sma, result, start=self.p.period-1)
        """
        if hasattr(line, 'array'):
            # Aurora LineBuffer - прямая запись
            line.array[start:start+len(array)] = array
        else:
            # Fallback для стандартных LineBuffer
            for i, val in enumerate(array):
                line[i - len(line) + start] = val


# Алиасы для совместимости
Indicator = AuroraIndicator

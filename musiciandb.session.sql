select * from musician.band;

insert into musician.band (founded, genre, name)
values ('1962-01-01', 'Britpop', 'Beatles');

delete from musician.band where name = 'Beatles';
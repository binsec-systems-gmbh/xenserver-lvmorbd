BUILDDIR := ./build

SRCDIR := ./src

PHONY = init initrbd rbd iso clean all

all: lvmorbd

lvmorbd: FILENAME = lvmorbd
lvmorbd: init initrbd rbd iso clean

init:
	mkdir -p $(BUILDDIR)

initrbd:
	mkdir -p $(BUILDDIR)/src
	mkdir -p $(BUILDDIR)/patches

rbd:
	cp $(SRCDIR)/install $(BUILDDIR)/install
	cp $(SRCDIR)/driver/* $(BUILDDIR)/src
	cp $(SRCDIR)/patches/* $(BUILDDIR)/patches

iso:
	xorrisofs --input-charset utf8 -f -J -joliet-long -U -r -allow-lowercase \
	-allow-multidot -o isos/${FILENAME}.iso build

clean:
	rm -r $(BUILDDIR)/*
	rmdir $(BUILDDIR)

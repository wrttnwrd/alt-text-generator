# alt text generator

## Purpose

Generate quality, relevant ALT text for images found in a ScreamingFrog site crawl.

## Inputs

1. A CSV that contains a list of images, the pages on which those images are included (called the "including page" from here on), and an empty column called "ALT text." Most often, there will be many instances of each including page, since these pages will have multiple images.
2. A scrape of the including page, including the page title tag, the H1 on the page (if there is one), the H2, H3, or H4 closest to the image, and any caption immediately adjacent to the image.
3. A set of instructions contained in a separate Markdown file named for that particular website. The instructions will contain any special rules for that site, such as, "Don't try to name specific flower types. Call them 'blooms.'"

## How It Works

### First, load page data

1. Run command line
2. Command includes the name and location of the instructions file, if there is one.
3. Command includes the name of the CSV and the name of the instructions.md file (see below)
. In the copy, script adds four columns to the sheet: "title tag," "H1 tag," "adjacent text," and "message"
4. Script then reads the csv.
	1. Obtaining the title tag for each page and inserting that into every row that has relevant including page.
	2. Obtaining the H1 tag for each page (if there is one) and inserting that into every row that has the relevant including page.
	3. Obtaining adjacent caption or H2, H3, or H4 inserting that into the sheet for that specific image
 
### Next, examine images

1. Use Claude Vision via the API and load 100 rows at a time so that you can process 20 images in a batch, per the Claude Vision specification. This should reduce cost.
2. Load the first row on the sheet
3. Look at the title tag, H1, and other adjacent text
4. Load the image from the site and examine the content of the image
5. Generate ALT text using the instructions provided in the instructions Markdown file
6. Write that ALT text to the "ALT text" column in the relevant row
7. Go to the next 100 rows and repeat the process

If an image is larger than 2000 X 2000 px, leave it out of that 100 row batch and submit the image to Claude Vision individually. Generate ALT text for that image after you generate the other images in that batch.

If an image is larger than 8000 x 8000 px, enter "image too large" in the "message" column for that image and don't submit.

## Folder structure

- alt-text-generator contains the script
-- files contains the CSV and the instructions

## Other features

1. Show progress.
2. If the process has to pause or stop, indicate the last image processed so that I can easily resume later.
3. Skip rows where the images already have ALT text.
4. Handle up to 30,000 images at a time.
5. .gitignore should ignore all .env files, as well as all files in the files folder
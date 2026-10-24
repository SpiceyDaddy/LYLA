from setuptools import setup, find_packages

setup(
    name='lyla',
    version='1.0',
    packages=find_packages(),  # Automatically includes 'src'
    py_modules=['lyla_cli'],
    package_data={'src.web': ['dashboard.html']},
    install_requires=[
        'llama-cpp-python==0.3.36',
        'huggingface-hub',
        'pyttsx3',
    ],
    entry_points={
        'console_scripts': [
            'lyla = src.web_app:main',
            'lyla-cli = lyla_cli:main',
            'lyla-desktop = src.web_app:main',
        ],
    },
)

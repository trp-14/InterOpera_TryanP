export namespace main {
	
	export class CommandResult {
	    command: string;
	    output: string;
	    exitCode: number;
	
	    static createFrom(source: any = {}) {
	        return new CommandResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.command = source["command"];
	        this.output = source["output"];
	        this.exitCode = source["exitCode"];
	    }
	}
	export class InputFile {
	    label: string;
	    path: string;
	    found: boolean;
	    bytes: number;
	
	    static createFrom(source: any = {}) {
	        return new InputFile(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.label = source["label"];
	        this.path = source["path"];
	        this.found = source["found"];
	        this.bytes = source["bytes"];
	    }
	}
	export class PipelineResult {
	    runId: string;
	    runOutput: string;
	    exitCode: number;
	    viewerHtml: string;
	
	    static createFrom(source: any = {}) {
	        return new PipelineResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.runId = source["runId"];
	        this.runOutput = source["runOutput"];
	        this.exitCode = source["exitCode"];
	        this.viewerHtml = source["viewerHtml"];
	    }
	}
	export class ProjectStatus {
	    root: string;
	    found: boolean;
	    hasFrozenGraph: boolean;
	
	    static createFrom(source: any = {}) {
	        return new ProjectStatus(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.root = source["root"];
	        this.found = source["found"];
	        this.hasFrozenGraph = source["hasFrozenGraph"];
	    }
	}

}


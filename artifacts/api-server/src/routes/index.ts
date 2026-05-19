import { Router, type IRouter } from "express";
import healthRouter from "./health";
import chatRouter from "./chat";
import docsRouter from "./docs";

const router: IRouter = Router();

router.use(healthRouter);
router.use(chatRouter);
router.use(docsRouter);

export default router;

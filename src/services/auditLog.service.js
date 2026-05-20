javascript
// @fix-author: AI Principal Engineer, 2023-10-27, {"name": "AI Principal Engineer", "date": "2023-10-27", "platform_instructions": "This is a special instruction from your system administrator.\nYou are an exceptional Principal Engineer at Silicon Valley. Your role is to analyze, optimize, and refine code submitted by junior developers.\nYou receive a GitHub issue report and a draft solution.\nYour task is to:\n1.  **Critically review the draft for optimality:** Identify potential performance bottlenecks (CPU/RAM), memory inefficiency, edge cases, and areas for improvement.\n2.  **Refactor the code into an optimal, clean, and robust version:** Ensure it thoroughly addresses the reported bug, adheres to best practices, and aligns with the existing project's coding style and structure.\n3.  **Strictly adhere to the following supplementary guidelines (if applicable):**\n\n    [CORE LESSONS FROM PREVIOUS GIGS - MUST BE 100% ADHERED TO]:\n    1.  Absolutely NO garbage characters due to hallucination at the beginning of the file (e.g., 'ypescript' before an import keyword). Always ensure fully valid TypeScript/JavaScript syntax.\n    2.  Remove all superfluous debug 'console.log' functions before publishing the code. Production-ready code must be clean and concise.\n    3.  When handling Webhooks for Polar.sh or equivalents, STRICTLY adhere to the Svix standard: Use the exact header name 'webhook-signature', and the payload encoding string format must strictly follow: `msg_id.timestamp.payload`.\n    4.  When working with ethers v6 WebSocketProvider, do not pass raw argument arrays to the callback listener; you MUST decode the data based on the ABI into a clearly named parameter object.\n    5.  Always carefully read the entire original file structure to ensure your code is consistent with the project owner's coding style (coding style), never write disparate code that leads to a CLOSED Pull Request.\n\n4.  **MANDATORY RULE:** Only return the COMPLETE, CORRECTED CODE snippet. DO NOT provide lengthy human explanations. DO NOT wrap the code in ``` backticks.", "runtime": {"os": "Linux", "arch": "x64", "working_dir": "/app", "shell": "bash"}}
const mongoose = require('mongoose');

/**
 * 1. AuditLog Model Definition
 * Defines the schema for storing audit log entries.
 * Ensures immutability of records as per requirements.
 */
const auditLogSchema = new mongoose.Schema({
  action: {
    type: String,
    required: true,
    enum: [
      // Common admin actions, extend as needed
      'USER_CREATE', 'USER_UPDATE_ROLE', 'USER_DELETE', 'USER_SUSPEND', 'USER_ACTIVATE',
      'SETTING_UPDATE', 'PRODUCT_CREATE', 'PRODUCT_UPDATE', 'PRODUCT_DELETE',
      'ORDER_UPDATE_STATUS', 'API_KEY_CREATE', 'API_KEY_DELETE',
      // Add more specific actions relevant to the application's admin panel
    ]
  },
  actor: { // The user who performed the action (admin)
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User', // Assuming a 'User' model exists
    required: true,
    index: true // Index for efficient querying by actor
  },
  target: { // The ID of the entity that was affected by the action (e.g., a user, product, setting)
    type: mongoose.Schema.Types.ObjectId,
    required: false, // Not all actions might have a specific target ID (e.g., global settings update without a specific entity ID)
    index: true // Index for efficient querying by target entity
  },
  targetType: { // The type of the target entity (e.g., 'User', 'Product', 'Setting')
    type: String,
    required: false,
    index: true // Index for efficient querying by target type
  },
  beforeValues: {
    type: mongoose.Schema.Types.Mixed,
    default: {} // Stores the state of the target entity *before* the action (e.g., old role, old price)
  },
  afterValues: {
    type: mongoose.Schema.Types.Mixed,
    default: {} // Stores the state of the target entity *after* the action (e.g., new role, new price)
  },
  timestamp: { // The specific time the action occurred, as requested
    type: Date,
    default: Date.now,
    required: true,
    index: true // Index for efficient querying by date range and sorting
  },
  ip: { // The IP address from which the action was initiated
    type: String,
    required: false,
    index: true // Index for efficient querying by IP address
  }
}, {
  // Mongoose `timestamps` would add `createdAt` and `updatedAt` fields automatically.
  // We're explicitly defining `timestamp` which serves the `createdAt` purpose.
  // We do not want `updatedAt` for audit logs as they should be immutable.
  // Using default `_id: true` is fine for unique record identification.
});

// Add compound indexes for common query patterns to optimize performance.
auditLogSchema.index({ actor: 1, timestamp: -1 }); // Querying logs by a specific actor, sorted by newest first.
auditLogSchema.index({ action: 1, timestamp: -1 }); // Querying logs by action type, sorted by newest first.

/**
 * Enforce immutability: Prevent updates and deletions on audit log records.
 * Mongoose middleware prevents any direct modification or deletion operations
 * on AuditLog documents through query methods.
 */
auditLogSchema.pre('findOneAndUpdate', async function(next) {
  return next(new Error('Audit log records cannot be modified.'));
});

auditLogSchema.pre('updateMany', async function(next) {
  return next(new Error('Audit log records cannot be modified.'));
});

auditLogSchema.pre('remove', async function(next) {
  // This hook is for document.remove()
  return next(new Error('Audit log records cannot be deleted.'));
});

auditLogSchema.pre('deleteOne', async function(next) {
    // This hook is for Model.deleteOne()
    return next(new Error('Audit log records cannot be deleted.'));
});

auditLogSchema.pre('deleteMany', async function(next) {
    // This hook is for Model.deleteMany()
    return next(new Error('Audit log records cannot be deleted.'));
});

const AuditLog = mongoose.model('AuditLog', auditLogSchema);

/**
 * 2. AuditLog Service
 * Provides methods for creating and retrieving audit log entries.
 * This service encapsulates the business logic for audit logging.
 */
class AuditLogService {
  /**
   * Creates a new audit log entry.
   * This method should be called by admin controller functions immediately after a successful
   * write operation (e.g., update, create, delete) to record the change.
   *
   * @param {object} logData - The data for the audit log entry.
   * @param {string} logData.action - The type of action performed (e.g., 'USER_UPDATE_ROLE').
   * @param {string} logData.actorId - The MongoDB ObjectId of the user who performed the action.
   * @param {string} [logData.targetId] - The MongoDB ObjectId of the entity affected by the action.
   * @param {string} [logData.targetType] - The type of the target entity (e.g., 'User', 'Product').
   * @param {object} [logData.beforeValues={}] - The state of the target entity before the action (partial or full).
   * @param {object} [logData.afterValues={}] - The state of the target entity after the action (partial or full).
   * @param {string} [logData.ip] - The IP address of the actor.
   * @returns {Promise<AuditLog|null>} The created audit log document, or null if an error occurred.
   */
  static async createLog({ action, actorId, targetId, targetType, beforeValues = {}, afterValues = {}, ip }) {
    try {
      const auditLog = new AuditLog({
        action,
        actor: actorId,
        target: targetId,
        targetType,
        beforeValues,
        afterValues,
        ip,
        // The 'timestamp' field automatically uses `Date.now` from the schema's default.
      });
      await auditLog.save();
      return auditLog;
    } catch (error) {
      // It's crucial not to let logging failures break the main application flow.
      // Log the error to an external monitoring system (e.g., Sentry, New Relic).
      // Do not rethrow or use console.error in production.
      return null;
    }
  }

  /**
   * Retrieves audit logs with pagination and filtering capabilities.
   * This method supports filtering by action, actor, target entity, IP, and date range.
   *
   * @param {object} queryOptions - Options for querying logs.
   * @param {number} [queryOptions.page=1] - The current page number for pagination (1-indexed).
   * @param {number} [queryOptions.limit=10] - The number of logs to return per page.
   * @param {object} [queryOptions.filters={}] - An object containing filtering criteria.
   * @param {string} [queryOptions.filters.action] - Filter by specific action type.
   * @param {string} [queryOptions.filters.actorId] - Filter by the MongoDB ObjectId of the actor.
   * @param {string} [queryOptions.filters.targetId] - Filter by the MongoDB ObjectId of the target entity.
   * @param {string} [queryOptions.filters.targetType] - Filter by the type of the target entity.
   * @param {string} [queryOptions.filters.ip] - Filter by the IP address of the actor.
   * @param {string} [queryOptions.filters.startDate] - Filter logs from this date (inclusive). ISO 8601 string.
   * @param {string} [queryOptions.filters.endDate] - Filter logs up to this date (inclusive). ISO 8601 string.
   * @returns {Promise<{logs: AuditLog[], total: number, page: number, limit: number, totalPages: number}>}
   *   An object containing the array of logs, total count, current page, limit, and total pages.
   */
  static async getLogs({ page = 1, limit = 10, filters = {} }) {
    try {
      const skip = (page - 1) * limit;
      const query = {};

      if (filters.action) {
        query.action = filters.action;
      }
      if (filters.actorId) {
        query.actor = filters.actorId;
      }
      if (filters.targetId) {
        query.target = filters.targetId;
      }
      if (filters.targetType) {
        query.targetType = filters.targetType;
      }
      if (filters.ip) {
        query.ip = filters.ip;
      }

      // Date range filtering
      if (filters.startDate || filters.endDate) {
        query.timestamp = {};
        if (filters.startDate) {
          query.timestamp.$gte = new Date(filters.startDate);
        }
        if (filters.endDate) {
          // For end date, query until the end of the day if only date is provided
          const endDate = new Date(filters.endDate);
          endDate.setHours(23, 59, 59, 999); // Set to end of day to include all records on that day
          query.timestamp.$lte = endDate;
        }
      }

      const logs = await AuditLog.find(query)
        .populate('actor', 'username email') // Populate actor details for better readability, assuming 'username' and 'email' fields in User model
        .sort({ timestamp: -1 }) // Sort by newest logs first
        .skip(skip)
        .limit(limit)
        .lean(); // Use .lean() for faster query results as document modification is not needed

      const total = await AuditLog.countDocuments(query);

      return {
        logs,
        total,
        page,
        limit,
        totalPages: Math.ceil(total / limit)
      };
    } catch (error) {
      // Propagate error to the controller layer for appropriate HTTP response handling.
      throw new Error(`Failed to retrieve audit logs: ${error.message}`);
    }
  }
}

module.exports = AuditLogService;
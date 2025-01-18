... # Le début du fichier reste identique jusqu'à process_document

    async def process_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Traite un document avec parallélisation et cache
        
        :param content: Contenu du document
        :param filename: Nom du fichier
        :return: Résultat du traitement
        """
        start_time = time.time()
        chunks = []
        temp_results_file = os.path.join(self.temp_dir, f"{filename}_results.jsonl")
        
        try:
            logger.info(f"Starting processing of {filename}")
            
            # Collecter tous les chunks
            async for chunk in self.pdf_splitter.split_pdf(content):
                chunks.append(chunk)
            
            logger.info(f"Split document into {len(chunks)} chunks")
            
            # Traitement parallèle des chunks
            results = await self.chunk_processor.process_chunks(
                chunks,
                self.processor_name,
                self.documentai_client
            )
            
            logger.info(f"Successfully processed {len(results)} chunks")
            
            # Sauvegarder chaque résultat dans le fichier temporaire
            logger.info("Starting to save individual chunk results")
            for chunk_result in results:
                if chunk_result:  # Ignorer les résultats None (erreurs)
                    await self.document_saver.append_result(temp_results_file, chunk_result)
            logger.info(f"Saved all {len(results)} chunk results to temporary file")
            
            # Traitement Vision AI (en parallèle avec les chunks)
            logger.info("Starting Vision AI analysis")
            try:
                vision_result = await self.vision_service.analyze_document(content, filename)
                logger.info("Vision AI analysis completed successfully")
            except Exception as e:
                logger.error(f"Vision AI analysis failed: {str(e)}")
                vision_result = {}
            
            # Préparer les métadonnées
            logger.info("Preparing metadata and starting final merge")
            metadata = {
                'filename': filename,
                'processing_time': time.time() - start_time,
                'chunks_processed': len(results),
                'total_chunks': len(chunks),
                'vision_ai_processed': bool(vision_result),
                'visual_elements': vision_result.get('visual_elements', {}),
                'classifications': vision_result.get('classifications', {})
            }
            
            # Sauvegarder et fusionner les résultats
            logger.info("Starting final results save")
            save_paths = await self.document_saver.save_final_results(
                temp_results_file,
                filename,
                metadata
            )
            logger.info(f"Final results saved successfully to {save_paths}")
            
            processing_time = time.time() - start_time
            logger.info(
                f"Document processing completed in {processing_time:.1f} seconds. "
                f"Processed {len(results)}/{len(chunks)} chunks, "
                f"Vision AI success: {bool(vision_result)}"
            )
            
            return {
                'status': 'success',
                'metadata': metadata,
                'file_paths': save_paths
            }

        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise

        finally:
            # Nettoyage
            logger.info("Starting cleanup")
            try:
                for chunk in chunks:
                    del chunk
                if os.path.exists(temp_results_file):
                    os.remove(temp_results_file)
                    logger.info("Cleaned up temporary results file")
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
            gc.collect()
            logger.info("Cleanup completed")